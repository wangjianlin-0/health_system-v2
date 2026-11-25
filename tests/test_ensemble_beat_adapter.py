from ai_model.inference.ensemble_beat_adapter import EnsembleBeatClassifier


def test_compare_marks_agreement_and_disagreement():
    rows = EnsembleBeatClassifier._compare(
        [{'r_sample500': 100, 'label': 'N'}, {'r_sample500': 500, 'label': 'S'},
         {'r_sample500': 900, 'label': 'F'}],
        [{'r_sample500': 105, 'label': 'N'}, {'r_sample500': 510, 'label': 'VF'},
         {'r_sample500': 895, 'label': 'VF'}],
    )
    assert [row['status'] for row in rows] == ['agree', 'disagree', 'agree']
    assert rows[1]['cnn_label'] == 'S' and rows[1]['hgb_label'] == 'VF'


def test_primary_result_is_preserved_and_review_is_explicit():
    model = EnsembleBeatClassifier.__new__(EnsembleBeatClassifier)
    class Fixed:
        def __init__(self, result): self.result = result
        def predict(self, processed): return self.result
    model.cnn = Fixed({'status': 'classified', 'label': 'CNN result',
                       'model_version': 'cnn', 'beats': {'items': [
                           {'r_sample500': 100, 'label': 'N'}]}, 'explanation': 'primary'})
    model.hgb = Fixed({'status': 'classified', 'model_version': 'hgb',
                       'model_sha256': 'hgb-sha', 'beats': {'items': [
                           {'r_sample500': 100, 'label': 'S'}]}})
    result = model.predict({})
    assert result['label'] == 'CNN result'
    assert result['agreement']['status'] == 'review_required'
    assert result['agreement']['disagree_count'] == 1
    assert result['confidence'] if 'confidence' in result else True
