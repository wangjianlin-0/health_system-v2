"""Offline export: python -m hardware.export_ads input.csv output_dir"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from signal_processing.python.ecg_preprocessing import parse_csv, process

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    data = args.input.read_bytes()
    signal = parse_csv(data.decode('utf-8-sig'), 500)
    result = process(signal)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, values in [('raw_mV.csv', result['waveform_raw_mV']),
                         ('rhythm_filtered_mV.csv', result['waveform_processed_mV'])]:
        with (args.output_dir / name).open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['mv'])
            writer.writerows((format(v, '.12g'),) for v in values)
    meta = {k:v for k,v in result.items() if not k.startswith('waveform')}
    meta.update(input_file=args.input.name, sha256=hashlib.sha256(data).hexdigest(),
                sample_count=len(result['waveform']), calibration='nominal_vendor_confirmed_not_measured')
    (args.output_dir / 'metadata.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(meta, ensure_ascii=True))

if __name__ == '__main__':
    main()
