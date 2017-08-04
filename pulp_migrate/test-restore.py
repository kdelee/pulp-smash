# coding=utf-8
"""Tests that a content on a populated server is present and useable."""

from urllib.parse import urljoin

import unittest

from pulp_smash import api, utils, config
from pulp_smash.constants import (
    REPOSITORY_PATH,
    RPM,
)
from pulp_migrate.constants import (
    RPM_REPO,
    PYTHON_REPO,
    DOCKER_V1_REPO,
    DOCKER_V2_REPO,
)

from pulp_migrate.utils import download_rpm


class BaseRestoreTestCase(unittest.TestCase):
    """Base class for all restored content tests.

    Provides a server config object.
    """

    @classmethod
    def setUpClass(cls):
        """Provide a server config object and api client.

        The following class attributes are created this method:

        ``cfg``
            A :class:`pulp_smash.config.PulpSmashConfig` object.
        ``client``
            A :class:`pulp_smash.api.Client` object.
            Uses a `pulp_smash.api.json_handler` handler so that the
            client returns the json response from the call.
        """
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)


class TestRPMRepo(BaseRestoreTestCase):
    """Test populated RPM repos."""

    def test_all(self):
        """Test that repo is present, sync-able, and has content."""
        repo_path = '{}/'.format(RPM_REPO)
        repo = {'_href': urljoin(REPOSITORY_PATH, repo_path)}
        sync_report = utils.sync_repo(self.cfg, repo)
        api.poll_spawned_tasks(self.cfg, sync_report.json())
        units = utils.search_units(self.cfg, repo)
        self.assertGreater(len(units), 0, 'No units found in repo')
        download_rpm(RPM_REPO, RPM)


class TestPythonRepo(BaseRestoreTestCase):
    """Test that the Python repo is present and functional."""

    def test_all(self):
        """Test that repo is present, sync-able, and has content."""
        repo_path = '{}/'.format(PYTHON_REPO)
        repo = {'_href': urljoin(REPOSITORY_PATH, repo_path)}
        sync_report = utils.sync_repo(self.cfg, repo)
        api.poll_spawned_tasks(self.cfg, sync_report.json())
        units = utils.search_units(self.cfg, repo)
        self.assertGreater(len(units), 0, 'No units found in repo')


class TestDockerRepo(BaseRestoreTestCase):
    """Test that the Docker repos are present and functional."""

    def test_v1(self):
        """Test that repo is present, sync-able, and has content."""
        repo_path = '{}/'.format(DOCKER_V1_REPO)
        repo = {'_href': urljoin(REPOSITORY_PATH, repo_path)}
        sync_report = utils.sync_repo(self.cfg, repo)
        api.poll_spawned_tasks(self.cfg, sync_report.json())
        units = utils.search_units(self.cfg, repo)
        self.assertGreater(len(units), 0, 'No units found in repo')

    def test_v2(self):
        """Test that repo is present, sync-able, and has content."""
        repo_path = '{}/'.format(DOCKER_V2_REPO)
        repo = {'_href': urljoin(REPOSITORY_PATH, repo_path)}
        sync_report = utils.sync_repo(self.cfg, repo)
        api.poll_spawned_tasks(self.cfg, sync_report.json())
        units = utils.search_units(self.cfg, repo)
        self.assertGreater(len(units), 0, 'No units found in repo')
