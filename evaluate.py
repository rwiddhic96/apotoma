from sklearn.linear_model import LogisticRegressionCV
from sklearn.metrics import roc_curve, auc
import numpy as np

def compute_roc(probs_neg, probs_pos):
    probs = np.concatenate((probs_neg, probs_pos))
    labels = np.concatenate((np.zeros_like(probs_neg), np.ones_like(probs_pos)))
    fpr, tpr, _ = roc_curve(labels, probs)
    auc_score = auc(fpr, tpr)

    return fpr, tpr, auc_score

def _auc_roc(test_sa, adv_sa, split=1000):
    tr_test_sa = np.array(test_sa[:split])
    tr_adv_sa = np.array(adv_sa[:split])

    tr_values = np.concatenate(
        (tr_test_sa.reshape(-1, 1), tr_adv_sa.reshape(-1, 1)), axis=0
    )
    tr_labels = np.concatenate(
        (np.zeros_like(tr_test_sa), np.ones_like(tr_adv_sa)), axis=0
    )

    lr = LogisticRegressionCV(cv=5, n_jobs=-1).fit(tr_values, tr_labels)

    ts_test_sa = np.array(test_sa[split:])
    ts_adv_sa = np.array(adv_sa[split:])
    values = np.concatenate(
        (ts_test_sa.reshape(-1, 1), ts_adv_sa.reshape(-1, 1)), axis=0
    )
    labels = np.concatenate(
        (np.zeros_like(ts_test_sa), np.ones_like(ts_adv_sa)), axis=0
    )

    probs = lr.predict_proba(values)[:, 1]

    _, _, auc_score = compute_roc(
        probs_neg=probs[: (len(test_sa) - split)],
        probs_pos=probs[(len(test_sa) - split):],
    )

    return auc_score