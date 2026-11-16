"""DB budget / API admission knobs: defaults are the contract values (12 / 8 / 16); invalid values fail closed."""
import os
import unittest
from unittest.mock import patch

from contracts.primitives import ContractError
from infrastructure import resources


class AdmissionKnobs(unittest.TestCase):
    def test_contract_defaults_are_unchanged(self):
        self.assertEqual((resources.DB_BUDGET_DEFAULT, resources.API_ADMISSION_DEFAULT, resources.API_WAIT_DEFAULT), (12, 8, 16))
        with patch.dict(os.environ, {}, clear=False):
            for name in ('BTL_DB_BUDGET', 'BTL_API_ADMISSION_LIMIT', 'BTL_API_ADMISSION_WAIT_LIMIT'):
                os.environ.pop(name, None)
            gate = resources.ApiAdmission(app=None)
            self.assertEqual((gate.budget.limit, gate.wait_limit), (8, 16))
        self.assertEqual(resources.DATABASE.limit, int(os.environ.get('BTL_DB_BUDGET') or 12))

    def test_knobs_apply_and_validate(self):
        with patch.dict(os.environ, {'BTL_API_ADMISSION_LIMIT': '12', 'BTL_API_ADMISSION_WAIT_LIMIT': '24'}):
            gate = resources.ApiAdmission(app=None)
            self.assertEqual((gate.budget.limit, gate.wait_limit), (12, 24))
        for bad in ('0', '65', '-1', '3.5', 'x', '１２'):
            with patch.dict(os.environ, {'BTL_API_ADMISSION_LIMIT': bad}):
                with self.assertRaises(ContractError, msg=bad):
                    resources.ApiAdmission(app=None)
        self.assertEqual(resources._env_int('BTL_DB_BUDGET_TEST', 12, 1, 64), 12)
        with patch.dict(os.environ, {'BTL_DB_BUDGET_TEST': '24'}):
            self.assertEqual(resources._env_int('BTL_DB_BUDGET_TEST', 12, 1, 64), 24)
        with patch.dict(os.environ, {'BTL_DB_BUDGET_TEST': '65'}):
            with self.assertRaises(ContractError):
                resources._env_int('BTL_DB_BUDGET_TEST', 12, 1, 64)

    def test_explicit_constructor_arguments_still_win(self):
        with patch.dict(os.environ, {'BTL_API_ADMISSION_LIMIT': '30'}):
            gate = resources.ApiAdmission(app=None, limit=2, wait_limit=3)
            self.assertEqual((gate.budget.limit, gate.wait_limit), (2, 3))


if __name__ == '__main__':
    unittest.main()
