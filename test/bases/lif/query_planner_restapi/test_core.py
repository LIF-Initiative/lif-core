import os
import unittest
from unittest.mock import patch


class TestMyModule(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "LIF_QUERY_PLANNER_INFORMATION_SOURCES_CONFIG_PATH": os.path.dirname(__file__)
            + "/test_information_sources_config.yml"
        },
    )
    def test_core(self):
        from lif.query_planner_restapi import core

        assert core is not None
