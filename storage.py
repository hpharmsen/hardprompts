import json
import os
from typing import List, Dict, Tuple, Optional


class Storage:
    """
    Class to store and retrieve results from a JSONL file.
    """

    def __init__(self, filename: str = "data/results.jsonl"):
        """Creates the storage file if it does not exist yet."""
        self.filename = filename
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', encoding='utf-8'):
                pass

    def _read_all(self) -> List[Dict]:
        """Reads all records from the storage file."""
        with open(self.filename, 'r', encoding='utf-8') as f:
            return [json.loads(line) for line in f]

    def _write_all(self, data: List[Dict]):
        """Writes all records to the storage file."""
        with open(self.filename, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

    def filter(self, models: List[str], test_names: List[str]) -> List[Dict]:
        data = self._read_all()
        return [record for record in data if record['model'] in models and record['test_name'] in test_names]

    def add(self, model: str, test_name: str, result: str, duration: float):
        """Saves one result to the storage file."""
        data = self._read_all()
        new_record = {"model": model,
                      "test_name": test_name,
                      "result": result,
                      "duration": round(duration, 3) if duration else None}
        data.append(new_record)
        self._write_all(data)

    def read(self, model: str, test_name: str) -> Tuple[Optional[str], Optional[float], int]:
        """Returns result, avg duration and number of stored passes for one model/test."""
        data = self.filter([model], [test_name])
        if not data:
            result = None
        elif all(record['result'] == data[0]['result'] for record in data):
            result = data[0]['result']
        else:
            # Mixed results: report how many passes were correct
            result = str(len([record for record in data if record['result'] == '√']))
        durations = [record['duration'] for record in data if record['duration']]
        duration = sum(durations) / len(durations) if durations else None
        return result, duration, len(data)

    def get_last_n(self, model: str, test_names: List[str], n: int) -> Tuple[int, float | None]:
        """Returns correct count and avg duration over the last n results per test."""
        data = self.filter([model], test_names)
        # Group by test_name and take last n per test
        by_test = {}
        for record in data:
            test = record['test_name']
            by_test.setdefault(test, []).append(record)

        correct = 0
        durations = []
        for test_name in test_names:
            records = by_test.get(test_name, [])[-n:]
            for r in records:
                if r['result'] == '√':
                    correct += 1
                elif r['result'] and r['result'].isdigit():
                    correct += int(r['result'])
                if r['duration']:
                    durations.append(r['duration'])

        avg_duration = sum(durations) / len(durations) if durations else None
        return correct, avg_duration
