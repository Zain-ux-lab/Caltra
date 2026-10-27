from backend.config import env_file


def test_existing_project_env_is_preserved(tmp_path):
    project=tmp_path/'project';project.mkdir();(project/'.env').touch()
    assert env_file(project,tmp_path/'home')==project/'.env'


def test_cloud_project_uses_existing_local_key_file(tmp_path):
    home=tmp_path/'home';private=home/'.config/caltra/.env';private.parent.mkdir(parents=True);private.touch()
    assert env_file(tmp_path/'cloud-project',home)==private


def test_new_install_without_private_config_uses_project_default(tmp_path):
    assert env_file(tmp_path/'project',tmp_path/'home')==tmp_path/'project/.env'
