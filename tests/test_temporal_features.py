import pandas as pd

from fraud_lab.data import chronological_split, load_paysim
from fraud_lab.features import GRAPH_COLUMNS, TemporalGraph, base_features


def transactions() -> pd.DataFrame:
    return pd.DataFrame({
        "step": [1, 1, 2, 3],
        "type": ["TRANSFER"] * 4,
        "amount": [100.0] * 4,
        "nameOrig": ["A", "C", "D", "A"],
        "oldbalanceOrg": [500.0] * 4,
        "nameDest": ["B", "B", "B", "D"],
        "oldbalanceDest": [0.0] * 4,
        "isFraud": [1, 0, 0, 0],
        "newbalanceOrig": [400.0] * 4,
        "isFlaggedFraud": [1] * 4,
    })


def test_same_step_cannot_see_siblings_or_own_label():
    graph = TemporalGraph(snapshot_interval=100)
    features = graph.transform(transactions(), learn_labels=True)
    assert list(features.columns) == GRAPH_COLUMNS
    assert features.loc[0, "receiver_degree"] == 0
    assert features.loc[1, "receiver_degree"] == 0
    assert features.loc[2, "receiver_degree"] == 2
    assert features.loc[2, "receiver_fraud_rate"] == 0.5
    assert features.loc[3, "sender_fraud_rate"] == 1.0


def test_validation_labels_do_not_update_neighbor_rate():
    graph = TemporalGraph(snapshot_interval=100)
    train = transactions().iloc[:2]
    graph.transform(train, learn_labels=True)
    graph.transform(transactions().iloc[2:3], learn_labels=False)
    assert graph.row_features("D", "B")[-1] == 0.5


def test_post_event_fields_have_no_effect_on_base_features():
    first = transactions().iloc[:1].copy()
    changed = first.copy()
    changed["newbalanceOrig"] = 0
    changed["isFlaggedFraud"] = 0
    pd.testing.assert_frame_equal(base_features(first), base_features(changed))


def test_split_keeps_whole_steps_separate():
    data = transactions()
    # Add enough steps and both labels in each window.
    data = pd.concat([data.assign(step=i, isFraud=[0, 1, 0, 1]) for i in range(1, 11)])
    train, validation, test, _ = chronological_split(data)
    assert set(train.step).isdisjoint(validation.step)
    assert set(validation.step).isdisjoint(test.step)
    assert train.step.max() < validation.step.min() < test.step.min()


def test_sampling_windows_are_disjoint(tmp_path):
    data = pd.concat([transactions().assign(step=i) for i in range(1, 101)], ignore_index=True)
    data["nameOrig"] = [f"A{i}" for i in range(len(data))]
    path = tmp_path / "sample.csv"
    data.to_csv(path, index=False)
    first = load_paysim(path, sample_fraction=0.25, seed=42, sample_start=0.0)
    second = load_paysim(path, sample_fraction=0.25, seed=42, sample_start=0.25)
    assert set(first.nameOrig).isdisjoint(second.nameOrig)
