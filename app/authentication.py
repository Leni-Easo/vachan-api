"""Authentication related functions"""
import os
import json
import requests
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
#pylint: disable=E0401
#pylint gives import error if not relative import is used. But app(uvicorn) doesn't accept it
from custom_exceptions import GenericException , PermisionException , AlreadyExistsException

PUBLIC_BASE_URL = os.environ.get("KRATOS_PUBLIC_BASE_URL", "http://127.0.0.1:4433/self-service/")
ADMIN_BASE_URL = os.environ.get("KRATOS_ADMIN_BASE_URL", "http://127.0.0.1:4434/")
USER_SESSION_URL = os.environ.get("KRATOS_USER_SESSION_URL",\
     "http://127.0.0.1:4433/sessions/whoami")
SUPER_USER = os.environ.get("SUPER_USERNAME")
SUPER_PASSWORD = os.environ.get("SUPER_PASSWORD")

access_roles = {
    "contentType" : ["SuperAdmin","VachanAdmin"],
    "licenses" : ["SuperAdmin","VachanAdmin"],
    "versions" : ["SuperAdmin","VachanAdmin"],
    "sources" : ["SuperAdmin","VachanAdmin"],
    "bibles" : ["SuperAdmin","VachanAdmin"],
    "commentaries" : ["SuperAdmin","VachanAdmin"],
    "dictionaries" : ["SuperAdmin","VachanAdmin"],
    "infographics" : ["SuperAdmin","VachanAdmin"],
    "bibleVideos" : ["SuperAdmin","VachanAdmin"],
    "userRole" :["SuperAdmin"],
    "delete_identity":["SuperAdmin"]
}

#Roles based on app
app_based_role = {
    "ag":"aguser",
    "vachan":"vachanuser"
}

#check roles for api
def verify_role_permision(api_name,permision):
    """check the user roles for the requested api"""
    verified = False
    if api_name in access_roles:
        access_list = access_roles[api_name]
        if len(access_list) != 0 and len(permision) != 0:
            for role in permision:
                if role in access_list:
                    verified = True
        else:
            raise PermisionException("User have no permision to access API")
    else:
        raise GenericException("No permisions set for the API - %s"%api_name)
    return verified

#Class handles the session validation and logout
class AuthHandler():
    """Authentication class"""
    security = HTTPBearer()
    #pylint: disable=R0201
    def kratos_session_validation(self,auth:HTTPAuthorizationCredentials = Security(security)):
        """kratos session validity check"""
        recieve_token = auth.credentials
        headers = {}
        headers["Accept"] = "application/json"
        headers["Authorization"] = f"Bearer {recieve_token}"

        user_data = requests.get(USER_SESSION_URL, headers=headers)
        data = json.loads(user_data.content)
        roles = []
        if user_data.status_code == 200:
            if "userrole" in data["identity"]["traits"]:
                roles = data["identity"]["traits"]["userrole"]

        elif user_data.status_code == 401:
            raise HTTPException(status_code=401, detail=data["error"])

        elif user_data.status_code == 500:
            raise GenericException(data["error"])

        return roles

    def kratos_logout(self,auth:HTTPAuthorizationCredentials= Security(security)):
        """logout function"""
        recieve_token = auth.credentials
        payload = {"session_token": recieve_token}
        headers = {}
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        logout_url = PUBLIC_BASE_URL + "logout/api"
        response = requests.delete(logout_url, headers=headers, json=payload)
        if response.status_code == 204:
            data = {"message":"Successfully Logged out"}
        elif response.status_code == 400:
            data = json.loads(response.content)
            raise HTTPException(status_code=401, detail=data["error"])
        elif response.status_code == 500:
            data = json.loads(response.content)
            raise GenericException(data["error"])
        return data

#get all user details
def get_all_kratos_users():
    """get all user info"""
    base_url = ADMIN_BASE_URL+"identities/"

    response = requests.get(base_url)
    if response.status_code == 200:
        user_data = json.loads(response.content)
    else:
        raise HTTPException(status_code=401, detail=json.loads(response.content))
    return user_data

#User registration with credentials
#pylint: disable=R0914
#pylint: disable=R1710
#pylint: disable=R0912
def user_register_kratos(register_details):
    """user registration kratos"""
    email = register_details.email
    password = register_details.password
    firstname = register_details.firstname
    lastname = register_details.lastname
    appname = register_details.appname

    appname = appname.lower()
    #check auto role assign
    #pylint: disable=R1715
    if appname in app_based_role:
        user_role = app_based_role[appname]
    else:
        user_role = "None"

    register_url = PUBLIC_BASE_URL+"registration/api"
    reg_flow = requests.get(register_url)
    #pylint: disable=R1702
    if reg_flow.status_code == 200:
        flow_res = json.loads(reg_flow.content)
        reg_flow_id = flow_res["ui"]["action"]
        reg_data = {"traits.email": email,
                     "traits.name.first": firstname,
                     "traits.name.last": lastname,
                     "password": password,
                     "traits.userrole":user_role,
                     "method": "password"}
        headers = {}
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        reg_req = requests.post(reg_flow_id,headers=headers,json=reg_data)
        reg_response = json.loads(reg_req.content)
        #pylint: disable=R1705
        if reg_req.status_code == 200:
            name_path = reg_response["identity"]["traits"]["name"]
            data={
                "details":"Registration Successfull",
                "registered_details":{
                    "id":reg_response["identity"]["id"],
                    "email":reg_response["identity"]["traits"]["email"],
                    "Name":str(name_path["first"]) + " " + str(name_path["last"]),
                    "Permisions": reg_response["identity"]["traits"]["userrole"]
                },
                "token":reg_response["session_token"]
            }
            return data
        elif reg_req.status_code == 400:
            if "messages" in reg_response["ui"]:
                err_msg = \
        "An account with the same identifier (email, phone, username, ...) exists already."
                err_txt = reg_response["ui"]["messages"][0]["text"]
                if err_txt == err_msg:
                    kratos_users = get_all_kratos_users()
                    for user in kratos_users:
                        if email == user["traits"]["email"]:
                            current_user_id = user["id"]
                            if user_role not in user["traits"]["userrole"]:
                                role_list = [user_role]
                                return_data = user_role_add(current_user_id,role_list)
                                if return_data["Success"]:
                                    data={
                                        "details":"User Already Registered, New Permision updated",
                                        "registered_details":{
                                            "id":current_user_id,
                                            "email":email,
                                            "Permisions": return_data["role_list"]
                                            }
                                    }
                                    return data
                                else:
                                    return return_data
                            else:
                                raise HTTPException(status_code=reg_req.status_code, \
                                    detail=reg_response["ui"]["messages"][0]["text"])
                else:
                    raise HTTPException(status_code=reg_req.status_code,\
                         detail=reg_response["ui"]["messages"][0]["text"])

def user_login_kratos(auth_details):
    "kratos login"
    username = auth_details.username
    password =  auth_details.password
    data = {"details":"","token":""}

    login_url = PUBLIC_BASE_URL+"login/api/"
    flow_res = requests.get(login_url)
    if flow_res.status_code == 200:
        flow_res = json.loads(flow_res.content)
        flow_id = flow_res["ui"]["action"]

        cred_data = {"password_identifier": username, "password": password, "method": "password"}
        login_req = requests.post(flow_id, json=cred_data)
        if login_req.status_code == 200:
            login_req = json.loads(login_req.content)
            session_id = login_req["session_token"]
            data["details"] = "Login Succesfull"
            data["token"] = session_id
        else:
            raise HTTPException(status_code=401, detail="Invalid Credential")
        return data

#delete an identity
def delete_identity(user_id):
    """delete identity"""
    base_url = ADMIN_BASE_URL+"identities/"+user_id
    response = requests.delete(base_url)
    return response

#user role add
def user_role_add(user_id,roles_list):
    """user role add from admin"""
    base_url = ADMIN_BASE_URL+"identities/"
    url = base_url + str(user_id)

    response = requests.get(url)
    if response.status_code == 200:
        user_data = json.loads(response.content)

    else:
        raise HTTPException(status_code=401, detail=json.loads(response.content))

    schema_id = user_data["schema_id"]
    state = user_data["state"]
    traits = user_data["traits"]
    exist_roles = []

    if "" in roles_list or len(roles_list) == 0:
        roles_list = ["None"]

    for role in roles_list:
        if role in traits["userrole"]:
            exist_roles.append(role)
        else:
            traits["userrole"].append(role)
    roles_list = traits["userrole"]

    data = {
    "schema_id": schema_id,
    "state": state,
    "traits": traits
    }
    #pylint: disable=R1720
    if len(exist_roles) > 0:
        raise AlreadyExistsException("Already Exist permisions %s"%exist_roles)
    else:
        headers = {}
        headers["Content-Type"] = "application/json"
        response = requests.put(url,headers=headers,json=data)

        if response.status_code == 200:
            resp_data = json.loads(response.content)
            #pylint: disable=R1705
            if roles_list == resp_data["traits"]["userrole"]:
                return {"Success":True,"details":"User Roles Updated",
                        "role_list": resp_data["traits"]["userrole"]
                }
            else:
                return {"Success":False,"details":"Something went wrong .. Try again!"}
        else:
            raise HTTPException(status_code=401, detail=json.loads(response.content))

#Create Super User
def create_super_user():
    """function to create super user on startup"""
    super_user_url = ADMIN_BASE_URL+ "identities"
    found = False
    response = requests.get(super_user_url)
    if response.status_code == 200:
        identity_data = json.loads(response.content)
        for identity in identity_data:
            if SUPER_USER ==  identity["traits"]["email"]:
                found = True
    else:
        raise HTTPException(status_code=401, detail=json.loads(response.content))

    if not found:
        register_url = PUBLIC_BASE_URL+"registration/api"
        reg_flow = requests.get(register_url)
        if reg_flow.status_code == 200:
            flow_res = json.loads(reg_flow.content)
            reg_flow_id = flow_res["ui"]["action"]
            reg_data = {"traits.email": SUPER_USER,
                        "traits.name.first": "Super",
                        "traits.name.last": "Admin",
                        "password": SUPER_PASSWORD,
                        "traits.userrole":"SuperAdmin",
                        "method": "password"}
            headers = {}
            headers["Accept"] = "application/json"
            headers["Content-Type"] = "application/json"
            reg_req = requests.post(reg_flow_id,headers=headers,json=reg_data)
            if reg_req.status_code == 200:
                print("Super Admin Created")
            elif reg_req.status_code == 400:
                raise HTTPException(status_code=401, detail="Error on creating Super Admin")
    else:
        print("Super Admin already exist")
