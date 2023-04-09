import json

import random

import requests

import datetime

from sqlalchemy import sql

from flask_restx import Namespace, Resource
from flask import Blueprint, render_template, request, redirect

from CTFd.forms import Forms
from CTFd.api import CTFd_API_v1
from CTFd.utils.user import get_ip
from CTFd.utils.uploads import delete_file
from CTFd.api.v1.challenges import Challenge
from CTFd.utils.user import is_admin, get_current_user
from CTFd.plugins import register_plugin_assets_directory
from CTFd.utils.decorators import authed_only, admins_only
from CTFd.plugins.flags import FlagException, get_flag_class
from CTFd.plugins.challenges import BaseChallenge, CHALLENGE_CLASSES
from CTFd.models import db, Users, Solves, Fails, Flags, ChallengeFiles, Tags, Hints, Challenges



PLUGIN_CHALLENGE_TYPE_NAME = "instancied"
PLUGIN_ASSETS_DIRECTORY = "/plugins/Ctfdockerized/assets/"


def log(string, level="INFO"):
    now = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{now} [{level}] : {string}")



# ---------DOCKER API SECTION---------
def get_server_url(server_id):
    """
    Simply returns the formatted url from a server_id
    """
    docker_server = DockerServers.query.filter_by(id=server_id).first()
    return f"http://{docker_server.address}:{docker_server.port}"


def get_images_from_server(server_id):
    """
    Send a web request to the docker server and retrieve
    all images
    """
    docker_url = f"{get_server_url(server_id)}/images/json"
    images = requests.get(docker_url).json()
    return images

def get_image_exposed_port  (server_id, image_name):
    docker_url = f"{get_server_url(server_id)}/images/{image_name}/json?all=1"
    
    print("")
    r = requests.get(docker_url)
    if r.status_code != 200:
        return None

    return list(r.json()['Config']['ExposedPorts'].keys())[0]   # We support only 1 port 

def get_instances_info(server_id):
    """
    Send a web request to the docker server and retrieve
    all instances info
    """
    docker_url = get_server_url(server_id)


def get_free_port(server_id):
    """
    Find a free port from the server
    """
    used_ports = [ci.instance_port for ci in CurrentInstances.query.filter_by(server_id=server_id).all()]
    port = 0
    while port == 0:
        if (np := random.randint(40000, 50000)) not in used_ports:
            port = np
    
    return port


def create_docker_container(instance):
    """
    Create an instance on a remote server
    """
    create_instance_url = f"{get_server_url(instance.server_id)}/containers/create"
    image = InstanciedChallenges.query.filter_by(id=instance.challenge_id).first().docker_image
    host_port = instance.instance_port
    docker_port = get_image_exposed_port(instance.server_id, image)
    if docker_port is None or len(docker_port) == 0:
        now = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        docker_server = DockerServers.query.filter_by(id=server_id).first()
        log(f"Can't create container for image {image}@{docker_server}, no exposed ports or image does not exist", "ERROR")
        return

    headers = {'Content-type': 'application/json'}
    data = json.dumps({
            "Image": image,
            "ExposedPorts": {
                f"{docker_port}/tcp": {},
            },
            "HostConfig": {"PortBindings": {docker_port: [{"HostPort": str(host_port)}]}},
            "StopTimeout": 7200  # 2H before stop
    })

    r = requests.post(create_instance_url, data=data, headers=headers)
    response = r.json()
    if r.status_code != 201:
        log(f"Can't create container : {response}", "ERROR")
        return None
    return response['Id']


def start_docker_container(instance):
    """
    Start an instance on a remote server
    """
    start_instance_url = f"{get_server_url(instance.server_id)}/containers/{instance.container_id}/start"

    headers = {'Content-type': 'application/json'}
    
    r = requests.post(start_instance_url, headers=headers)
    if r.status_code != 204:
        log(f"Can't start container : {r.json()}", "ERROR")
        return False
    return True

def stop_docker_container(instance):
    """
    Stop an instance on a remote server
    """
    start_instance_url = f"{get_server_url(instance.server_id)}/containers/{instance.container_id}/stop"

    headers = {'Content-type': 'application/json'}
    
    r = requests.post(start_instance_url, headers=headers)
    if r.status_code != 204:
        log(f"Can't stop container : {r.json()}", "ERROR")
        return False
    return True


# ------------------------------------

class DockerServers(db.Model):
    """
    Database table to list all the Docker servers that have been configurated.
    >   id
        name
        address
        port
        docker_images
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text)
    address = db.Column(db.Text)
    port = db.Column(db.Integer)
    docker_images = db.Column(db.Text)


class CurrentInstances(db.Model):
    """
    Database table to keep track of every instance that has been started at
    any point during the CTF
    >   instance_id
        challenge_id
        user_id
        docker_server
        docker_port
        docker_image
        status
        creation_date
    """
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('challenges.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    server_id = db.Column(db.Integer, db.ForeignKey('docker_servers.id'))
    container_id = db.Column(db.Text)
    instance_port = db.Column(db.Integer)
    status = db.Column(db.Boolean)
    creation_date = db.Column(db.DateTime(timezone=True), default=sql.func.now())


# basic ChallengeType object [https://docs.ctfd.io/docs/plugins/challenge-types]
class InstanciedChallengesType(BaseChallenge):
    id = PLUGIN_CHALLENGE_TYPE_NAME
    name = PLUGIN_CHALLENGE_TYPE_NAME

    templates = {
        'create': PLUGIN_ASSETS_DIRECTORY + "create.html",
        'update': PLUGIN_ASSETS_DIRECTORY + "update.html",
        'view':   PLUGIN_ASSETS_DIRECTORY + "view.html",
    }
    scripts = {
        'create': PLUGIN_ASSETS_DIRECTORY + "create.js",
        'update': PLUGIN_ASSETS_DIRECTORY + "update.js",
        'view':   PLUGIN_ASSETS_DIRECTORY + "view.js",
    }

    route = PLUGIN_ASSETS_DIRECTORY

    @staticmethod
    def create(request):
        """
        This method is used to process the challenge creation request.

        :param request:
        :return:
        """
        data = request.form or request.get_json()
        challenge = InstanciedChallenges(**data)
        db.session.add(challenge)
        db.session.commit()
        return challenge

    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.
        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        challenge = InstanciedChallenges.query.filter_by(id=challenge.id).first()
        data = {
            "id": challenge.id,
            "name": challenge.name,
            "value": challenge.value,
            "description": challenge.description,
            "docker_server": challenge.server_id,
            "docker_image": challenge.docker_image,
            "connection_info": challenge.connection_info,
            "next_id": challenge.next_id,
            "category": challenge.category,
            "state": challenge.state,
            "max_attempts": challenge.max_attempts,
            "type": challenge.type,
            "type_data": {
                "id": cls.id,
                "name": cls.name,
                "templates": cls.templates,
                "scripts": cls.scripts,
            },
        }
        return data

    @classmethod
    def update(cls, challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.
        :param challenge:
        :param request:
        :return:
        """
        data = request.form or request.get_json()
        for attr, value in data.items():
            setattr(challenge, attr, value)

        db.session.commit()
        return challenge

    @classmethod
    def delete(cls, challenge):
        """
        This method is used to delete the resources used by a challenge.
        :param challenge:
        :return:
        """
        Fails.query.filter_by(challenge_id=challenge.id).delete()
        Solves.query.filter_by(challenge_id=challenge.id).delete()
        Flags.query.filter_by(challenge_id=challenge.id).delete()
        files = ChallengeFiles.query.filter_by(challenge_id=challenge.id).all()
        for f in files:
            delete_file(f.id)
        ChallengeFiles.query.filter_by(challenge_id=challenge.id).delete()
        Tags.query.filter_by(challenge_id=challenge.id).delete()
        Hints.query.filter_by(challenge_id=challenge.id).delete()
        CurrentInstances.query.filter_by(challenge_id=challenge.id).delete()
        InstanciedChallenges.query.filter_by(id=challenge.id).delete()
        Challenges.query.filter_by(id=challenge.id).delete()
        db.session.commit()

        print("Deleting instance !")


    @classmethod
    def attempt(cls, challenge, request):
        """
        This method is used to check whether a given input is right or wrong. It does not make any changes and should
        return a boolean for correctness and a string to be shown to the user. It is also in charge of parsing the
        user's input from the request itself.
        :param challenge: The Challenge object from the database
        :param request: The request the user submitted
        :return: (boolean, string)
        """
        data = request.form or request.get_json()
        submission = data["submission"].strip()
        flags = Flags.query.filter_by(challenge_id=challenge.id).all()
        for flag in flags:
            try:
                if get_flag_class(flag.type).compare(flag, submission):
                    return True, "Correct"
            except FlagException as e:
                return False, str(e)
        return False, "Incorrect"


    @classmethod
    def solve(cls, user, team, challenge, request):
        """
        This method is used to insert Solves into the database in order to mark a challenge as solved.
        :param team: The Team object from the database
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        data = request.form or request.get_json()
        instances = CurrentInstances.query.filter_by(user_id=user.id, challenge_id=challenge.id, status=True).all()  # There should be only one but hey just in case
        for instance in instances:
            instance.status = False
            stop_docker_container(instance)
            db.session.commit()


        submission = data["submission"].strip()
        solve = Solves(
            user_id=user.id,
            team_id=team.id if team else None,
            challenge_id=challenge.id,
            ip=get_ip(req=request),
            provided=submission,
        )
        db.session.add(solve)
        db.session.commit()


    @classmethod
    def fail(cls, user, team, challenge, request):
        """
        This method is used to insert Fails into the database in order to mark an answer incorrect.
        :param team: The Team object from the database
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        data = request.form or request.get_json()
        submission = data["submission"].strip()
        wrong = Fails(
            user_id=user.id,
            team_id=team.id if team else None,
            challenge_id=challenge.id,
            ip=get_ip(request),
            provided=submission,
        )
        db.session.add(wrong)
        db.session.commit()


# basic Challenge object 
class InstanciedChallenges(Challenges):
    __mapper_args__ = {'polymorphic_identity': PLUGIN_CHALLENGE_TYPE_NAME}
    
    # No documentation to confirm this, but when creating a challenge, it will
    # actually create a new table in the database named after the class name
    # and will use the challenge.id as a primary and foreign key in this new
    # table to refer to the challenge.
    # If we want the docker_image associated with the challenge "test":
    #    > SELECT ic.docker_image FROM challenges c 
    #                JOIN instancied_challenges ic ON c.id = ic.id
    #                 WHERE c.name = "test";

    id = db.Column(None, db.ForeignKey('challenges.id'), primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('docker_servers.id'))
    docker_image = db.Column(db.Text)
    

def load_plugin_api(app):
    plugin_admin = Blueprint("plugin_admin", __name__, template_folder="templates", static_folder="assets")

    @plugin_admin.route("/admin/ctfdockerized/docker-servers/")
    @admins_only
    def admin_docker_servers():
        docker_servers = DockerServers.query.order_by(DockerServers.id).all()
        if len(request.args) == 1 and list(request.args.keys()) == ["data"] and request.args["data"] == "json":
            data = {}
            for server in docker_servers:
                image_names = []
                for image in get_images_from_server(server.id):
                    image_names.append(image['RepoTags'][0])

                server.docker_images = ','.join(image_names)
                db.session.commit()
                
                data[server.name] = {
                        "id": server.id,
                        "addr": server.address,
                        "port": server.port,
                        "img": server.docker_images
                    }
            return data
        return render_template("admin_docker_servers.html", servers=docker_servers)

    @plugin_admin.route("/admin/ctfdockerized/instances/")
    @admins_only
    def admin_instances():
        instances_list = []

        for instance in CurrentInstances.query.order_by(CurrentInstances.challenge_id).all():
            instances_list.append({
                        "id": instance.id,
                        "challenge": Challenges.query.filter_by(id=instance.challenge_id).first().name,
                        "username": Users.query.filter_by(id=instance.user_id).first().name,
                        "userid": instance.user_id,
                        "servername": DockerServers.query.filter_by(id=instance.server_id).first().name,
                        "status": CurrentInstances.query.filter_by(id=instance.id).first().status
                })

        return render_template("admin_all_instances.html", instances=instances_list)

    @plugin_admin.route("/admin/ctfdockerized/new-server/")
    @admins_only
    def add_new_server():
        # Create the server
        if len(request.args) == 3 and list(request.args.keys()) == ["name", "addr", "port"]:
            new_docker = DockerServers(
                name=request.args["name"],
                address=request.args["addr"],
                port=request.args["port"],
                docker_images="")
            db.session.add(new_docker)
            db.session.commit()

            image_names = []
            for image in get_images_from_server(new_docker.id):
                image_names.append(image['RepoTags'][0])

            new_docker.docker_images = ','.join(image_names)
            db.session.commit()
            return redirect("/admin/ctfdockerized/docker-servers/", code=302)
        return render_template("create_server.html")

    plugin_authed = Blueprint("plugin_authed", __name__, template_folder="templates", static_folder="assets")

    @plugin_authed.route("/ctfdockerized/start/")
    @authed_only
    def start_instance():
        # Start a new instance

        # If the request have 2 args, process it
        if len(request.args) == 2 and list(request.args.keys()) == ["server", "challenge"]:
            server_id = request.args["server"]
            challenge_id = request.args["challenge"]

            if DockerServers.query.filter_by(id=server_id).first() is None:
                return {"success": False}

            if InstanciedChallenges.query.filter_by(id=challenge_id).first() is None:
                return {"success": False}
          
            user_id = get_current_user().id
            port = get_free_port(server_id)

            new_instance = CurrentInstances(
                challenge_id=challenge_id,
                user_id=user_id,
                container_id="",
                server_id=server_id,
                instance_port=port,
                status=True
            )

            db.session.add(new_instance)
            chall = Challenges.query.filter_by(id=challenge_id).first()

            new_instance.container_id = create_docker_container(new_instance)
            start_docker_container(new_instance)
            db.session.commit()

            return {
                "success": True,
                "instance_id": new_instance.id,
                "address": DockerServers.query.filter_by(id=server_id).first().address,
                "port": new_instance.instance_port
            }

        # If the request only have 1 arg, we send the info
        if len(request.args) == 1 and list(request.args.keys()) == ["challenge_info"]:
            challenge_id = request.args["challenge_info"]
            user_id = get_current_user().id

            created_instances = CurrentInstances.query.filter_by(challenge_id=challenge_id, user_id=user_id).all()

            if created_instances is None:
                return {"exists": False}

            curr_instance = None
            for instance in created_instances:
                if instance.status:
                    curr_instance = instance
                    break

            if curr_instance is None:
                return {"exists": False}
            
            return {
                "exists": True,
                "instance_id": curr_instance.id,
                "address": DockerServers.query.filter_by(id=curr_instance.server_id).first().address,
                "port": curr_instance.instance_port
            }

        # If the request doesnt have args, redirect
        if is_admin():
            return redirect("/admin/ctfdockerized/instances/")
        return redirect("/challenges/")

    @plugin_authed.route("/ctfdockerized/stop/")
    @authed_only
    def stop_instance():
        if len(request.args) == 1 and list(request.args.keys()) == ["instance_id"]:
            instance_id = request.args["instance_id"]
            user = get_current_user()

            target_instance = CurrentInstances.query.filter_by(id=instance_id).first()

            if user.id != target_instance.challenge_id and not is_admin():
                return {"success": False}

            if target_instance is None or not target_instance.status:
                return {"success": True}

            target_instance.status = False
            db.session.commit()
            stop_docker_container(target_instance)

            return {"success": True}

        return redirect("/challenges")

    app.register_blueprint(plugin_admin)
    app.register_blueprint(plugin_authed)


# Main function called [https://docs.ctfd.io/docs/plugins/overview]
def load(app):
    app.db.create_all()
    CHALLENGE_CLASSES[PLUGIN_CHALLENGE_TYPE_NAME] = InstanciedChallengesType
    register_plugin_assets_directory(app, base_path=PLUGIN_ASSETS_DIRECTORY)
    load_plugin_api(app)
