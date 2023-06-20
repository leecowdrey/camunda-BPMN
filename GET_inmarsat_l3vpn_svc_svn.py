#
# (c) 2015-2019 Lumina Networks, Inc.
# 2077 Gateway Place, Suite 500, San Jose, CA 95110
# All rights reserved.
#
# Use of the software files and documentation is subject to license terms.
#
import json
import sys, traceback
import com.google.gson.JsonParser as JsonParser
import requests
from workflow_utility import utility
from delegate_tools import LogFormatter

#BEGIN: Custom Python Libraries for WFE:
import delegate_lib_constants
import controller
import lumina_plastic
import inventory_utils
import data_utils

#***BEGIN OPTIONAL - Reload when changes made to Library code
#**** Comment out section when not doing library development
reload(delegate_lib_constants)
reload(controller)
reload(lumina_plastic)
reload(inventory_utils)
reload(data_utils)
#***END OPTIONAL Reload

from delegate_lib_constants import DelegateConstants as dc
from inventory_utils import InventoryUtils
from controller import Controller
from lumina_plastic import Plastic
from data_utils import *
#END: Custom Python Libraries for WFE:

#LSC_IN_USER = "10.40.55.120" 
LSC_IN_USER =  "lsc"


#GLOBAL VARS:
logger = LogFormatter.logger('wfe.GetL3VPNsvc')
result = {}
parser = JsonParser()

provision_operation = dc.PROVISION_UPDATE #Set to dc.PROVISION_NBI_TEST/dc.PROVISION_UPDATE for active device interactions

sites = {
  "sites": {
    "site": [
    ]
  }
}

#BEGIN MAIN        
try:
  workflow_input = execution.getVariable(utility.constants.WORKFLOW_INPUT)#get the workflow input from restconf
  workflow_name = str(execution.getVariable(utility.constants.WORKFLOW_NAME))#get the workflow name

  logger.info("inputs: %s", workflow_input)
  logger.info("Activity: %s", workflow_name)

  # Lumina SDN Controller
  controller_1 = Controller(ip=LSC_IN_USER, port=8181)
  ops_url = controller_1.get_operations_url()
  translate_url = ops_url + "/jsonrpc:config/configured-endpoints/cartographer/yang-ext:mount/ldk-cartographer:translate"
  config_url = controller_1.get_config_url()
  logger.info("Successful controller instance created")
  netconf_topo_url = config_url + "/network-topology:network-topology/topology/topology-netconf" #/node/VMX-A1
  #Device Specific Configuration Vars:
  junos_conf_mount = "/network-topology:network-topology/topology/topology-netconf/node/{0}/yang-ext:mount/junos-conf-root:configuration"
  junos_vrf = "/junos-conf-routing-instances:routing-instances"
  junos_vrf_instance = "/instance/{0}"

  #VLAN configuration URI
  junos_infs  = "/junos-conf-interfaces:interfaces"
  junos_inf  = "/interface/{0}"
  junos_unit = "/unit/{0}"




  # NBI Response Results instance
  nbi_response = data_utils.NbiResults()

  # Lumina Service Mapper (Plastic)
  lsm_1 = Plastic(controller_class=controller_1)

  #LSM Vars:
  in_version = "1.0"
  out_version = "1.0"
  in_type = "json"
  out_type = "json"
  # Begin primary data processing
  for input in workflow_input:
    store = input.get("store")
    entity = input.get("entity").toString().replace('\"','')
    path = json.loads(input.get("path").toString())
    yang_module = data_utils.get_dict_top_key(path).split(":")[0]
    config_type = data_utils.get_dict_deepest_key(path)
    input_operation = input.get("operation").toString().replace('\"','')

    # Log variables:
    logger.info("LSC Mount store=%s", store)
    logger.info("LSC Mount entity=%s", entity)
    logger.info(path)
    logger.info("yang_module=%s", yang_module)
    logger.info("config_type=%s", config_type)
    logger.info("Request Operation=%s", input_operation)

    #For complete GET
    #http://34.217.54.147:38181/restconf/config/jsonrpc:config/configured-endpoints/inmarsat-l3vpn-svc-wfe/yang-ext:mount/inmarsat-l3vpn-svc:svn
    if config_type == yang_module+":svn":
      logger.info("Request for network wide data. Pull all nodes.")
      nc_topo = controller_1.http_get(netconf_topo_url)
      #logger.info("junipher out={0}".format(nc_topo))
 
      if nc_topo.status_code is not 404:
        nc_topo_text = json.loads(nc_topo.content)
        #logger.info(nc_topo_text)
        if "node" in nc_topo_text["topology"][0]:
          for n in nc_topo_text["topology"][0]["node"]:
            logger.info("Pull vrf for node=%s",n["node-id"]) 
            
            junos_vrf_url = config_url + junos_conf_mount.format(n["node-id"]) + junos_vrf
            vrfs_resp = controller_1.http_get(junos_vrf_url)
            if vrfs_resp.status_code is not 404:
              vrfs_resp_text = json.loads(vrfs_resp.content)
              for v in vrfs_resp_text["junos-conf-routing-instances:routing-instances"]["instance"]:
                site = {
                         "vpn-name": "",
                         "nodes": []
                       }
                index = get_index("vpn-name", v["name"], sites['sites']["site"])
                if index != -1 : 
                  sites['sites']["site"][index]["nodes"].append(n["node-id"])
                else:
                  site["vpn-name"] = v["name"]
                  site["nodes"].append(n["node-id"])
                  sites["sites"]["site"].append(site)
          result["success"] = True
        else:
          logger.info("Failed as no netconf nodes found on LSC")
          site = {
               "vpn-name": "ERROR:Failed as no netconf nodes found on LSC",
               "nodes": []
             }
          sites["sites"]["site"].append(site)
          result["success"] = False
      else:
        logger.info("Failed to get netconf nodes from LSC")
        site = {
                 "vpn-name": "ERROR:Failed to get netconf nodes.",
                 "nodes": []
               }
        sites["sites"]["site"].append(site)
        result["success"] = False
      result["data"] = sites
      if result["success"] == True:
        execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result["data"])
      else:
        result = data_utils.set_lsc_error_result(json.dumps(result["data"]))
        execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result)

    #GET all sites
    #http://lsc:8181/restconf/config/jsonrpc:config/configured-endpoints/inmarsat-l3vpn-svc-wfe/yang-ext:mount/inmarsat-l3vpn-svc:svn
    elif "sites" in config_type:
      logger.info("Request for network wide data. Pull all nodes.")
      nc_topo = controller_1.http_get(netconf_topo_url)
      #logger.info("junipher out={0}".format(nc_topo))
 
      if nc_topo.status_code is not 404:
        nc_topo_text = json.loads(nc_topo.content)
        #logger.info(nc_topo_text)
        if "node" in nc_topo_text["topology"][0]:
          for n in nc_topo_text["topology"][0]["node"]:
            logger.info("Pull vrf for node=%s",n["node-id"]) 
            
            junos_vrf_url = config_url + junos_conf_mount.format(n["node-id"]) + junos_vrf
            vrfs_resp = controller_1.http_get(junos_vrf_url)
            if vrfs_resp.status_code is not 404:
              vrfs_resp_text = json.loads(vrfs_resp.content)
              for v in vrfs_resp_text["junos-conf-routing-instances:routing-instances"]["instance"]:
                site = {
                         "vpn-name": "",
                         "nodes": []
                       }
                index = get_index("vpn-name", v["name"], sites['sites']["site"])
                if index != -1 : 
                  sites['sites']["site"][index]["nodes"].append(n["node-id"])
                else:
                  site["vpn-name"] = v["name"]
                  site["nodes"].append(n["node-id"])
                  sites["sites"]["site"].append(site)
          result["success"] = True
        else:
          logger.info("Failed as no netconf nodes found on LSC")
          site = {
               "vpn-name": "ERROR:Failed as no netconf nodes found on LSC",
               "nodes": []
             }
          sites["sites"]["site"].append(site)
          result["success"] = False
      else:
        logger.info("Failed to get netconf nodes from LSC")
        site = {
                 "vpn-name": "ERROR:Failed to get netconf nodes.",
                 "nodes": []
               }
        sites["sites"]["site"].append(site)
        result["success"] = False
      result["data"] = sites["sites"]
      if result["success"] == True:
        execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result["data"])
      else:
        result = data_utils.set_lsc_error_result(json.dumps(result["data"]))
        execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result) 
    #Get All nodes for given <SVN-Name>
    #http://lsc:8181/restconf/config/jsonrpc:config/configured-endpoints/inmarsat-l3vpn-svc-wfe/yang-ext:mount/inmarsat-l3vpn-svc:svn/sites/site/SVN4000
    elif "site" in config_type and "vpn-name" in config_type["site"][0]:
      user_query = str(config_type["site"][0]["vpn-name"])
      vpn_name  = get_vpn_name_query(user_query)
      vlan_name = get_vlan_name_query(user_query)
      dev_list  = get_device_list_query(user_query)
      logger.info("inputs vpn_name={0}, vlan={1}, device={2}".format(vpn_name, vlan_name, dev_list))

      if vpn_name is  None or not vpn_name.strip() or vpn_name.isspace():
        logger.info("Request for nodes with %s vlan-name.", vlan_name)
        site = {
              "vpn-name": vlan_name,
              "nodes": []
            }       
        vpn_name = None
      else:
        logger.info("Request for nodes with %s vpn-name. Ignoring vlan.", vpn_name)
        vlan_name = None 
        site = {
              "vpn-name": vpn_name,
              "nodes": []
            }
      #vpn_name = str(config_type["site"][0]["vpn-name"])
      #logger.info("Request for nodes with %s vpn-name.", vpn_name)
      nc_topo = controller_1.http_get(netconf_topo_url)
      #logger.info("junipher out={0}".format(nc_topo))

      if nc_topo.status_code is not 404:
        nc_topo_text = json.loads(nc_topo.content)
        #logger.info(nc_topo_text)
        if "node" in nc_topo_text["topology"][0]:
          for n in nc_topo_text["topology"][0]["node"]:
            if dev_list is not None:
              if n["node-id"] not in dev_list:
                logger.info("device {0} not in request list.".format(n["node-id"]))
                continue
            if vpn_name is not None:
              junos_vrf_ins_url = config_url + junos_conf_mount.format(n["node-id"]) + junos_vrf + junos_vrf_instance.format(vpn_name)
              vrfs_resp = controller_1.http_get(junos_vrf_ins_url)
              if vrfs_resp.status_code is not 404:
                logger.info("Found SVN at node=%s",n["node-id"])  
                site["nodes"].append(n["node-id"])
            elif vlan_name is not None:
              junos_inf_all = config_url + junos_conf_mount.format(n["node-id"]) + junos_infs 
              infs_resp = controller_1.http_get(junos_inf_all)
              get_vlan_list = str(n["node-id"]) + "::"
              if infs_resp.status_code is not 404:
                infs = json.loads(infs_resp.content) 
                for inf in infs["junos-conf-interfaces:interfaces"]["interface"]:
                  if "unit" in inf:
                    for u in inf["unit"]:
                      if vlan_name == u["name"]:
                        get_vlan_list = get_vlan_list + inf["name"] + ","
                if get_vlan_list == str(n["node-id"]) + "::":
                  result["success"] = False
                  logger.info("No VLAN found at node=%s", n["node-id"])     
                else:
                  logger.info("Found VLAN at node=%s", n["node-id"])     
                  get_vlan_list = get_vlan_list[:-1]
                  site["nodes"].append(get_vlan_list)
              else:
                result["success"] = False
                logger.info("Failed inteface query on node=%s",n["node-id"])
                #site["vpn-name"] = "Failed interfaces query on node=" + n["node-id"] + "."
#            else:
#              junos_vrf_url = config_url + junos_conf_mount.format(n["node-id"]) + junos_vrf
#              vrfs_resp = controller_1.http_get(junos_vrf_url)
#              if vrfs_resp.status_code is not 404:
#                vrfs_resp_text = json.loads(vrfs_resp.content)
#                for v in vrfs_resp_text["junos-conf-routing-instances:routing-instances"]["instance"]:
#                  site = {
#                           "vpn-name": "",
#                           "nodes": []
#                         }
#                  index = get_index("vpn-name", v["name"], sites['sites']["site"])
#                  if index != -1 : 
#                    sites['sites']["site"][index]["nodes"].append(n["node-id"])
#                  else:
#                    site["vpn-name"] = v["name"]
#                    site["nodes"].append(n["node-id"])
#                    sites["sites"]["site"].append(site)
#                site = sites["sites"]["site"][0]
          result["success"] = True
        else:
          logger.info("Failed as no netconf nodes found on LSC")
          site["vpn-name"] = "Failed as no netconf nodes found on LSC"
          result["success"] = False
      else:
        logger.info("Failed to get netconf nodes from LSC")
        site["vpn-name"] = "Failed to get netconf nodes."
        result["success"] = False
      result["data"] = site
      if result["success"] == True:
        execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result["data"])
      else:
        result = data_utils.set_lsc_error_result(json.dumps(result["data"]))
        execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result)
    #Get All SVN on given <Device Name as seen on LSC mount>
    #http://lsc:8181/restconf/config/jsonrpc:config/configured-endpoints/inmarsat-l3vpn-svc-wfe/yang-ext:mount/inmarsat-l3vpn-svc:svn/devices/MX204-1
    #elif "devices" in config_type and "role" in config_type["devices"][0]:
    else:
      result = data_utils.set_lsc_error_result("API not supported by WFE/WAL.")
      execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result)
except Exception as e:
  logger.info('Error: %s',e)
  logger.info("Internal error. please check wfe logs")
  result = data_utils.set_lsc_error_result("Internal error. please check wfe logs")
  execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result)
