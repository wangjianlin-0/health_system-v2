"""Compute metrics from supplied predictions without running a model."""
import argparse
import json
from pathlib import Path


def evaluate(rows):
    if not rows or any('true_label' not in row or 'predicted_label' not in row for row in rows):
        raise ValueError('需要非空真实预测列表，每行含 true_label 和 predicted_label')
    labels = sorted({row['true_label'] for row in rows} | {row['predicted_label'] for row in rows})
    matrix = {truth: {prediction: 0 for prediction in labels} for truth in labels}
    for row in rows:
        matrix[row['true_label']][row['predicted_label']] += 1
    per_class = {}
    for label in labels:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predicted = sum(matrix[truth][label] for truth in labels)
        precision = tp / predicted if predicted else 0
        recall = tp / support if support else 0
        per_class[label] = {'precision': precision, 'recall': recall, 'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0, 'support': support}
    return {'samples': len(rows), 'macro_f1': sum(item['f1'] for item in per_class.values()) / len(labels), 'per_class': per_class, 'confusion_matrix': matrix, 'status': 'computed_from_supplied_predictions'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='读取真实预测 JSON，不运行或假装已训练模型')
    parser.add_argument('predictions', type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(json.loads(args.predictions.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2))
