import json
import os
from typing import List, Dict, Tuple, Optional


class Storage:
    """
    Class to store and retrieve results from a JSONL file.
    """

    def __init__(self, filename: str = "storage.jsonl"):
        """
        Initializes the Storage object.

        Args:
            filename (str): The name of the file to store the data in.
        """
        self.filename = filename
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', encoding='utf-8') as f:
                pass

    def _read_all(self) -> List[Dict]:
        """Reads all records from the storage file."""
        if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
            return []
        with open(self.filename, 'r', encoding='utf-8') as f:
            return [json.loads(line) for line in f]

    def _write_all(self, data: List[Dict]):
        """Writes all records to the storage file."""
        with open(self.filename, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

    def save(self, model: str, testcase: str, passes: int, result: str, duration: float):
        """
        Saves a result to the storage file.
        If a result with the same model, testcase and passes already exists, it will be updated.

        Args:
            model (str): The model name.
            testcase (str): The testcase identifier.
            passes (int): The number of passes.
            result (str): The result of the testcase.
            duration (float): The duration of the testcase execution.
        """
        data = self._read_all()
        new_record = {"model": model, "testcase": testcase, "passes": passes, "result": result, "duration": duration}

        found = False
        for i, record in enumerate(data):
            if record.get("model") == model and record.get("testcase") == testcase and record.get("passes") == passes:
                data[i] = new_record
                found = True
                break

        if not found:
            data.append(new_record)

        self._write_all(data)

    def read(self, model: str, testcase: str, passes: int) -> Tuple[Optional[str], Optional[float]]:
        """
        Reads a result from the storage file.

        Args:
            model (str): The model name.
            testcase (str): The testcase identifier.
            passes (int): The number of passes.

        Returns:
            Tuple[Optional[str], Optional[float]]: The result and duration, or (None, None) if not found.
        """
        data = self._read_all()
        for record in data:
            if record.get("model") == model and record.get("testcase") == testcase and record.get("passes") == passes:
                return record.get("result"), record.get("duration")
        return None, None

    def reset(self):
        """
        Clears all data from the storage file.
        """
        if os.path.exists(self.filename):
            os.remove(self.filename)
        # Recreate the empty file
        with open(self.filename, 'w', encoding='utf-8') as f:
            pass