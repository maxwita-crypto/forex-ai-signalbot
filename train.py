"""Train on MANUALLY LABELLED historical signals, with chronological holdout."""
import sqlite3
from pathlib import Path
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.model_selection import train_test_split
from sklearn.calibration import CalibratedClassifierCV
ROOT=Path(__file__).parent
rows=sqlite3.connect(ROOT/'signals.sqlite3').execute("SELECT direction,entry,sl,tp,rsi,atr,outcome_r FROM signals WHERE outcome_r IS NOT NULL ORDER BY ts ASC").fetchall()
if len(rows)<200: raise SystemExit(f"Not enough labeled trades: {len(rows)}/200")
X=np.asarray([[r[4],r[5],abs(r[3]-r[1])/abs(r[1]-r[2]),int(r[0]=='BUY')] for r in rows])
y=np.asarray([int(r[6]>0) for r in rows]); cut=int(len(X)*0.8)
if len(set(y[:cut]))<2 or len(set(y[cut:]))<2: raise SystemExit("Need both win and loss classes in train/test periods")
# Calibration on temporally earlier block; last 20% remains untouched.
from sklearn.model_selection import TimeSeriesSplit
base=HistGradientBoostingClassifier(max_leaf_nodes=8,max_iter=60,l2_regularization=10,random_state=42)
model=CalibratedClassifierCV(base,cv=TimeSeriesSplit(n_splits=3),method="sigmoid")
model.fit(X[:cut],y[:cut]); p=model.predict_proba(X[cut:])[:,1]
auc=roc_auc_score(y[cut:],p); brier=brier_score_loss(y[cut:],p)
print(f"Holdout observations={len(p)} AUC={auc:.3f} Brier={brier:.3f}")
print("No automatic deployment. Review performance and data quality manually.")
joblib.dump(model,ROOT/'model_candidate.pkl')
print("Wrote model_candidate.pkl. Never copy to model.pkl without validating it.")
