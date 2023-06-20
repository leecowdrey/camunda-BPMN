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
import re

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
import time

#LSC_IN_USER = "10.40.55.120" 
LSC_IN_USER =  "lsc"


#GLOBAL VARS:
logger = LogFormatter.logger('wfe.DelL3VPNsvc')
result = {}
parser = JsonParser()

provision_operation =  dc.PROVISION_UPDATE #dc.PROVISION_NBI_TEST #Set to dc.PROVISION_UPDATE for active device interactions

#BEGIN MAIN        
try:
  workflow_input = execution.getVariable(utility.constants.WORKFLOW_INPUT)#get the workflow input from restconf
  workflow_name = str(execution.getVariable(utility.constants.WORKFLOW_NAME))#get the workflow name

  logger.info("inputs: %s", workflow_input)
  logger.info("Activity: %s", workflow_name)

  # Lumina SDN Controller
  controller_1 = Controller(ip=LSC_IN_USER, port=8181)
  ops_url = controller_1.get_operations_url()
  config_url = controller_1.get_config_url()
  logger.info("Successful controller instance created")
  netconf_topo_url = config_url + "/network-topology:network-topology/topology/topology-netconf" #/node/VMX-A1
  #Device Specific Configuration Vars:
  junos_mount = "/network-topology:network-topology/topology/topology-netconf/node/{0}/yang-ext:mount/junos-conf-root:configuration"
  junos_vrfs = "/junos-conf-routing-instances:routing-instances"
  junos_vrf_instance = "/instance/{0}"

  #VLAN configuration URI
  junos_infs  = "/junos-conf-interfaces:interfaces"
  junos_inf  = "/interface/{0}"
  junos_unit = "/unit/{0}"

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
    rt_msg = ""
    #http://lsc:8181/restconf/config/jsonrpc:config/configured-endpoints/inmarsat-l3vpn-svc-wfe/yang-ext:mount/inmarsat-l3vpn-svc:svn/sites/site/SVN4000
    if "site" in config_type and "vpn-name" in config_type["site"][0]:
     
      user_query = str(config_type["site"][0]["vpn-name"])
      vpn_name  = get_vpn_name_query(user_query)
      vlan_name = get_vlan_name_query(user_query)
      dev_list  = get_device_list_query(user_query)
      logger.info("inputs vpn_name={0}, vlan={1}, device={2}".format(vpn_name, vlan_name, dev_list))
      logger.info("Request for nodes with %s vpn-name.", vpn_name)
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
              #Delete all VRF instances.
              junos_vrf_ins_url = config_url + junos_mount.format(n["node-id"]) + junos_vrfs + junos_vrf_instance.format(vpn_name)
              if provision_operation == dc.PROVISION_NBI_TEST:
                vrfs_resp = controller_1.http_get(junos_vrf_ins_url)
              else:
                vrfs_resp = controller_1.http_delete(junos_vrf_ins_url)
              if vrfs_resp.status_code is not 404:
                logger.info("Deleted SVN at node=%s.",n["node-id"])  
                rt_msg = rt_msg + "\nDeleted SVN at node=" + n["node-id"] + "."
              else:
                logger.info("Failed as no SVN found at node=%s",n["node-id"])
                rt_msg = rt_msg + "\nFailed as no SVN found at node=" + n["node-id"] + "."
              time.sleep(1)

            if vlan_name is None:
              continue
            #TODO Delete all VLAN interfaces
            #1. build URL for VLAN 2. check vlan 3. delete vlan
            junos_inf_all = config_url + junos_mount.format(n["node-id"]) + junos_infs 
            infs_resp = controller_1.http_get(junos_inf_all)
            del_vlan_url = ""
            if infs_resp.status_code is not 404:
              infs = json.loads(infs_resp.content) 
              for inf in infs["junos-conf-interfaces:interfaces"]["interface"]:
                if "unit" in inf:
                  for u in inf["unit"]:
                    if vlan_name == u["name"]:
                      iname = controller_1.get_url_encoded_path("{"+inf["name"]+"}")
                      del_vlan_url = config_url + junos_mount.format(n["node-id"]) + junos_infs + junos_inf.format(iname) + junos_unit.format(vlan_name)
                      if provision_operation == dc.PROVISION_NBI_TEST:
                        del_resp = controller_1.http_get(del_vlan_url)
                      else:
                        del_resp = controller_1.http_delete(del_vlan_url)
                      if del_resp.status_code is not 404:
                        logger.info("Deleted VLAN at node=%s.",n["node-id"])  
                        rt_msg = rt_msg + "\nDeleted VLAN at node=" + n["node-id"] + "."
                      else:
                        logger.info("Failed to delete VLAN at node={0}. error={1}".format(n["node-id"],vlan_name))
                        rt_msg = rt_msg + "\nFailed to delete VLAN at node=" + n["node-id"] + "." + " error={0}".format(vlan_name)
                      time.sleep(1)
              if "" == del_vlan_url:
                logger.info("Failed as no VLAN found at node=%s",n["node-id"])
                rt_msg = rt_msg + "\nFailed as no VLAN found at node=" + n["node-id"] + "."
                     
            else:
              logger.info("Failed as inteface not found at node=%s",n["node-id"])
              rt_msg = rt_msg + "\nFailed as no interfaces found at node=" + n["node-id"] + "."
 
          if "Failed" in rt_msg:
            result = data_utils.set_lsc_error_result(rt_msg)
          else:
            result = data_utils.set_lsc_success_result(rt_msg)
        else:
          logger.info("Failed as no netconf nodes found on LSC")
          result = data_utils.set_lsc_error_result("Failed as no nodes found on LSC")
      else:
        logger.info("Failed to get netconf nodes from LSC")
        result = data_utils.set_lsc_error_result("Failed to get nodes from LSC")
    else:
      logger.info("API option not supported")
      result = data_utils.set_lsc_error_result("API option not supported")

  execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result)
except Exception as e:
  #logger.info('Error: %s',e)
  logger.info('Error: %s',traceback.format_exc())
  logger.info("Internal error. please check wfe logs")
  #result["data"] = {"error":"Internal error. please check wfe logs"}
  result = data_utils.set_lsc_error_result("Internal error. please check wfe logs")
  execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result)
 

