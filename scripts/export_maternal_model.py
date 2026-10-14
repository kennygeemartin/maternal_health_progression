"""Maintainer-only export of one inspected MIT-licensed pretrained artifact.

Dependencies (temporary tooling only): numpy==2.2.6, joblib==1.6.0,
catboost==1.2.8. Usage: python scripts/export_maternal_model.py SOURCE.joblib
This deliberately never imports or instantiates objects from the pickle's
sklearn/imblearn/pandas/CatBoost globals; they become inert metadata holders.
Only the extracted numerical CBM is decoded by CatBoost and exported as JSON.
"""
import argparse
import hashlib
import json
import pickle
import tempfile
from collections import OrderedDict
from pathlib import Path

import joblib
import numpy as np
from catboost import CatBoostClassifier
from joblib.numpy_pickle import NumpyUnpickler, NumpyArrayWrapper

SOURCE_SHA = "8dae3ed278947571f4edf8df8c34df00fd582000b2c1ee9bf264f3f410dbff5b"
SOURCE_REVISION = "f260b91bf8144b64a666996fc1acca6b4b1613ac"
FEATURES = ["Age","SystolicBP","DiastolicBP","BS","BodyTemp","HeartRate"]
INERT_GLOBALS = {
    ("imblearn.pipeline","Pipeline"),
    ("imblearn.over_sampling._smote.cluster","KMeansSMOTE"),
    ("sklearn.neighbors._unsupervised","NearestNeighbors"),
    ("sklearn.neighbors._kd_tree","newObj"), ("sklearn.neighbors._kd_tree","KDTree"),
    ("sklearn.metrics._dist_metrics","newObj"), ("sklearn.metrics._dist_metrics","EuclideanDistance64"),
    ("sklearn.cluster._kmeans","MiniBatchKMeans"),
    ("sklearn.compose._column_transformer","ColumnTransformer"),
    ("sklearn.compose._column_transformer","_RemainderColsList"),
    ("sklearn.preprocessing._data","StandardScaler"),
    ("pandas.core.indexes.base","_new_Index"), ("pandas.core.indexes.base","Index"),
    ("catboost.core","CatBoostClassifier"),
}

class Inert:
    def __new__(cls,*args,**kwargs):
        result=object.__new__(cls)
        result.constructor_args=args
        return result
    def __init__(self,*args,**kwargs):
        pass
    def __setstate__(self,state):
        if isinstance(state,dict):
            self.__dict__.update(state)
        elif isinstance(state,tuple):
            self.inert_state=state
        else:
            raise pickle.UnpicklingError("Unexpected object state")

class Restricted(NumpyUnpickler):
    inert_types = {}
    def find_class(self,module,name):
        basic = {("builtins","slice"):slice, ("collections","OrderedDict"):OrderedDict,
                 ("numpy","ndarray"):np.ndarray, ("numpy","dtype"):np.dtype,
                 ("joblib.numpy_pickle","NumpyArrayWrapper"):NumpyArrayWrapper,
                 ("numpy._core.multiarray","_reconstruct"):np._core.multiarray._reconstruct,
                 ("numpy._core.multiarray","scalar"):np._core.multiarray.scalar}
        key=(module,name)
        if key in basic:
            return basic[key]
        if key in INERT_GLOBALS:
            if key not in self.inert_types:
                self.inert_types[key]=type(name,(Inert,),{})
            return self.inert_types[key]
        raise pickle.UnpicklingError("Blocked unexpected global: "+module+"."+name)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("--output",type=Path,default=Path("backend/models/maternal_catboost.json"))
    args=parser.parse_args()
    # Pin the object-array reader whose nested find_class respects this restriction.
    if joblib.__version__ != "1.6.0":
        raise RuntimeError("Use inspected joblib==1.6.0 for this export")
    if hashlib.sha256(args.source.read_bytes()).hexdigest()!=SOURCE_SHA:
        raise RuntimeError("Source artifact changed: review it before changing this digest")
    with args.source.open("rb") as stream:
        pipeline=Restricted(str(args.source),stream,ensure_native_byte_order=True).load()
    steps=dict(pipeline.steps)
    preprocessor=steps["Preprocessing"]
    assert list(preprocessor.feature_names_in_)==FEATURES
    name,scaler,columns=preprocessor.transformers_[0]
    assert name=="Standard Scaler"
    assert list(columns.constructor_args[1]["data"])==FEATURES
    args.output.parent.mkdir(parents=True,exist_ok=True)
    native=CatBoostClassifier()
    native.load_model(blob=steps["Model"].__dict__["__model"])
    assert native.classes_.tolist()==[0,1,2]
    with tempfile.NamedTemporaryFile(dir=args.output.parent,suffix=".json",delete=False) as stream:
        output=Path(stream.name)
    try:
        native.save_model(str(output),format="json")
        original=json.loads(output.read_text())
    finally:
        output.unlink()
    assert not original["features_info"].get("categorical_features")
    assert [f["flat_feature_index"] for f in original["features_info"]["float_features"]]==list(range(6))
    trees=[]
    for tree in original["oblivious_trees"]:
        splits=tree.get("splits") or []
        assert all(s["split_type"]=="FloatFeature" for s in splits)
        assert len(tree["leaf_values"])==3*(1<<len(splits))
        trees.append({"splits":[[s["float_feature_index"],s["border"]] for s in splits],"leaves":tree["leaf_values"]})
    result={"format":"bloom-catboost-numeric-v1","features":FEATURES,"classes":["low","mid","high"],
        "mean":scaler.mean_.tolist(),"scale":scaler.scale_.tolist(),"scale_and_bias":original["scale_and_bias"],"trees":trees,
        "source_url":"https://github.com/viochris/Maternal-Health-Risk-Model-Research","source_revision":SOURCE_REVISION,
        "source_artifact_sha256":SOURCE_SHA,
        "reference_ranges":{"Age":[10,70],"SystolicBP":[70,160],"DiastolicBP":[49,100],"BS":[6,19],"BodyTemp":[98,103],"HeartRate":[60,90]}}
    raw=json.dumps(result,separators=(",",":"),allow_nan=False).encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(raw)
    print("Export SHA-256:",hashlib.sha256(raw).hexdigest())

if __name__=="__main__":
    main()
