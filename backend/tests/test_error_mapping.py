"""HTTP mapping of domain refusals that a user must be able to read (no database needed)."""
import json, unittest
from contracts.primitives import ContractError
from cloud.workspaces import domain_error_response


class ErrorMappingTests(unittest.TestCase):
    def body(self, code):
        response = domain_error_response(ContractError(code, 'dataset'))
        return response.status_code, json.loads(response.body)

    def test_session_pinned_to_an_earlier_dataset_is_a_clear_409_not_an_outage(self):
        status, body = self.body('REFUSED_DATASET_VERSION')
        self.assertEqual((status, body['detail']), (409, 'REFUSED_DATASET_VERSION'))

    def test_unknown_internal_errors_stay_masked_as_503(self):
        status, body = self.body('SOMETHING_INTERNAL')
        self.assertEqual((status, body['detail']), (503, 'SERVICE_UNAVAILABLE'))


if __name__ == '__main__':
    unittest.main()
