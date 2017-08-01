"""Clean up repositories created by pulp_migrate.populate tests"""
from urllib.parse import urljoin

from pulp_smash import api, config
from pulp_smash.constants import (
    REPOSITORY_PATH,
    ORPHANS_PATH
)

from pulp_smash.tests.rpm.api_v2.utils import (
    gen_distributor as gen_rpm_distributor,
    gen_repo as gen_rpm_repo
)

from pulp_smash.tests.python.api_v2.utils import (
    gen_repo as gen_python_repo,
    gen_distributor as gen_python_distributor
)

from pulp_smash.tests.puppet.api_v2.utils import (
    gen_repo as gen_puppet_repo,
    gen_distributor as gen_puppet_distributor
)

from pulp_smash.tests.docker.api_v2.utils import (
    gen_repo as gen_docker_repo,
    gen_distributor as gen_docker_distributor
)

def clean_repo(id):
    """Delete the repo with given id and any content left orphaned by it.

    Calls to clean_repo will only attempt to delete the repo and call to delete
    orphans if a repository with given id exists.
   """
    client = api.Client(config.get_config(), api.json_handler)
    repos = client.get(REPOSITORY_PATH)
    for repo in repos:
        if urljoin(REPOSITORY_PATH, id) in repo['_href']:
            client.delete(repo['_href'])
            client.delete(ORPHANS_PATH)
