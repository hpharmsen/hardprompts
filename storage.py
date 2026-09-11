import json
import os


def pass_score(result: str | None) -> float:
    """Points for one stored pass: '√' is 1, a numeric string its own value, anything else 0."""
    if result == '√':
        return 1.0
    try:
        return float(result)
    except (TypeError, ValueError):
        return 0.0


class Storage:
    """
    Class to store and retrieve results from a JSONL file.
    """

    def __init__(self, filename: str = 'data/results.jsonl'):
        """Creates the storage file if it does not exist yet."""
        self.filename = filename
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', encoding='utf-8'):
                pass

    def _read_all(self) -> list[dict]:
        """Reads all records, skipping a truncated last line from an interrupted run."""
        with open(self.filename, 'r', encoding='utf-8') as f:
            records = []
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return records

    def filter(self, models: list[str], test_names: list[str]) -> list[dict]:
        data = self._read_all()
        return [record for record in data if record['model'] in models and record['test_name'] in test_names]

    def add(self, model: str, test_name: str, result: str, duration: float, tokens: tuple[int, int] | None = None):
        """Appends one result to the storage file. tokens is (input, output) when the call
        completed; records written before token logging existed simply lack the fields."""
        record = {
            'model': model,
            'test_name': test_name,
            'result': result,
            'duration': round(duration, 3) if duration else None,
        }
        if tokens:
            record['tokens_in'], record['tokens_out'] = tokens
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def read(self, model: str, test_name: str) -> tuple[str | None, float | None, int]:
        """Returns result, avg duration and number of stored passes for one model/test."""
        data = self.filter([model], [test_name])
        if not data:
            result = None
        elif all(record['result'] == data[0]['result'] for record in data):
            result = data[0]['result']
        else:
            # Mixed results: report the average score per pass
            result = f'{sum(pass_score(record["result"]) for record in data) / len(data):g}'
        durations = [record['duration'] for record in data if record['duration']]
        duration = sum(durations) / len(durations) if durations else None
        return result, duration, len(data)

    def get_last_n(self, model: str, test_names: list[str], n: int) -> tuple[float, float | None]:
        """Returns correct count and avg duration over the last n results per test."""
        data = self.filter([model], test_names)
        # Group by test_name and take last n per test
        by_test = {}
        for record in data:
            test = record['test_name']
            by_test.setdefault(test, []).append(record)

        correct = 0.0
        durations = []
        for test_name in test_names:
            records = by_test.get(test_name, [])[-n:]
            for r in records:
                correct += pass_score(r['result'])
                if r['duration']:
                    durations.append(r['duration'])

        avg_duration = sum(durations) / len(durations) if durations else None
        return correct, avg_duration
