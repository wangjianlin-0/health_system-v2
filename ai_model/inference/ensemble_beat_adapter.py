"""CNN-primary/HGB-review adapter; never invents a fused class probability."""
from __future__ import annotations

from typing import Any

from ai_model.inference.edge_adapter import EdgeClassifier


class EnsembleBeatClassifier:
    model_version = 'CNN-H27-primary+HGB-v92-review'

    def __init__(self) -> None:
        self.cnn = EdgeClassifier('cnn')
        self.hgb = EdgeClassifier('hgb')

    def predict(self, processed: dict[str, Any]) -> dict[str, Any]:
        primary = self.cnn.predict(processed)
        review = self.hgb.predict(processed)
        if primary.get('status') != 'classified':
            return {**primary, 'review_model': review, 'agreement': {'status': 'unavailable'}}
        primary_items = (primary.get('beats') or {}).get('items') or []
        review_items = (review.get('beats') or {}).get('items') or []
        comparisons = self._compare(primary_items, review_items)
        disagreements = [row for row in comparisons if row['status'] == 'disagree']
        return {
            **primary,
            'model_version': self.model_version,
            'source': 'ensemble_review',
            'review_model': {
                'status': review.get('status'), 'model_version': review.get('model_version'),
                'model_sha256': review.get('model_sha256'),
            },
            'agreement': {
                'status': 'review_required' if disagreements else 'consistent',
                'matched_beats': len(comparisons),
                'agree_count': sum(row['status'] == 'agree' for row in comparisons),
                'disagree_count': len(disagreements),
                'unmatched_primary': sum(row['status'] == 'primary_only' for row in comparisons),
                'items': comparisons,
                'scope': 'CNN为主结果；HGB仅用于一致性复核，不生成融合置信度。',
            },
            'explanation': (primary.get('explanation') or '') +
                           (' 检测到CNN/HGB逐拍不一致，建议人工复核。' if disagreements else
                            ' CNN/HGB在可匹配心拍上一致。'),
        }

    @staticmethod
    def _compare(primary: list[dict[str, Any]], review: list[dict[str, Any]], tolerance: int = 75):
        used: set[int] = set()
        rows = []
        for beat in primary:
            pos = beat.get('r_sample500')
            candidates = [(abs(int(other.get('r_sample500', -10**9)) - int(pos)), index, other)
                          for index, other in enumerate(review) if index not in used]
            match = min(candidates, default=None)
            if match is None or match[0] > tolerance:
                rows.append({'sample': pos, 'cnn_label': beat.get('label'),
                             'hgb_label': None, 'status': 'primary_only'})
                continue
            _, index, other = match
            used.add(index)
            cnn_label = beat.get('label')
            hgb_label = other.get('label')
            comparable_hgb = 'V' if hgb_label == 'VF' else hgb_label
            comparable_cnn = 'V' if cnn_label == 'F' else cnn_label
            rows.append({'sample': pos, 'cnn_label': cnn_label, 'hgb_label': hgb_label,
                         'sample_delta': match[0],
                         'status': 'agree' if comparable_cnn == comparable_hgb else 'disagree'})
        return rows
