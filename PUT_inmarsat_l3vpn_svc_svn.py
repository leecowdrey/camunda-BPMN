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
import urllib

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
#END: Custom Python Libraries for WFE:

#LSC_IN_USER = "10.40.55.120" 
LSC_IN_USER =  "lsc"


#GLOBAL VARS:
logger = LogFormatter.logger('wfe.PutL3VPNsvc')
result = {}
parser = JsonParser()

provision_operation = dc.PROVISION_UPDATE #Set to dc.PROVISION_UPDATE for active device interactions or dc.PROVISION_NBI_TEST

sites = {
  "sites": {
    "site": [
    ]
  }
}

def get_index(key, value, lst):
  index = -1
  for i, obj in enumerate(lst):
    #logger.info("device->name=%s, value=%s",obj[key], value)
    if obj[key] == value:
      index = i
      break
  return index

#BEGIN MAIN        
try:
  workflow_input = execution.getVariable(utility.constants.WORKFLOW_INPUT)#get the workflow input from restconf
  workflow_name = str(execution.getVariable(utility.constants.WORKFLOW_NAME))#get the workflow name

  logger.info("inputs: %s", workflow_input)
  logger.info("Activity: %s", workflow_name)

  # Lumina SDN Controller
  controller_1 = Controller(ip=LSC_IN_USER, port=8181, timeout=120)
  ops_url = controller_1.get_operations_url()
  translate_url = ops_url + "/jsonrpc:config/configured-endpoints/cartographer/yang-ext:mount/ldk-cartographer:translate"
  config_url = controller_1.get_config_url()
  logger.info("Successful controller instance created")

  netconf_topo_url = config_url + "/network-topology:network-topology/topology/topology-netconf" #/node/VMX-A1
  #Device Specific Configuration Vars:
  junos_mount = "/network-topology:network-topology/topology/topology-netconf/node/{0}/yang-ext:mount/junos-conf-root:configuration"

  #VRF confuguration URI
  #{{lsc_connect}}/restconf/config/network-topology:network-topology/topology/topology-netconf/node/{{ne01_name}}/yang-ext:mount/junos-conf-root:configuration/junos-conf-routing-instances:routing-instances/instance/SVN5
  junos_vrfs = "/junos-conf-routing-instances:routing-instances"
  junos_vrf_instance = "/instance/{0}"

  #VLAN configuration URI
  #{{lsc_connect}}/restconf/config/network-topology:network-topology/topology/topology-netconf/node/{{ne01_name}}/yang-ext:mount/junos-conf-root:configuration/junos-conf-interfaces:interfaces/interface/ae0/unit/4000
  junos_inf  = "/junos-conf-interfaces:interfaces/interface/{0}"
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
  vpn_in_map = "inmarsat-l3vpn-svc-vpn-input"
  vlan_in_map = "inmarsat-l3vpn-svc-vlan-input"
  svc_out_map = "inmarsat-l3vpn-svc-output"
  junos_vlan_map = "odl-juniper-interface-unit-update-output"
  junos_vpn_map = "odl-juniper-l3vpn-routing-instance-update-output"
  
  #example input
  #[{"store":"config","entity":"inmarsat-l3vpn-svc-wfe","path":{"inmarsat-l3vpn-svc:svn":{}},"data":{"sites":{"site":[{"vpn-name":"SVN4000","type":"RAN","nodes":["MX204-1","MX204-2"]}]},"devices":[{"name":"RAN","vlan":[{"unit":"4000","address":"10.123.9.1/24","description":"vMXAgg-SVN4000","interface":"ae1"}],"routing-instance":{"target":"target:31515:14000","group":"SVN4000","route-distinguisher":"172.16.1.101:14000","as-local":"31515","interface":["ae0.2","ae1.2"],"instance-type":"vrf","as-peer":"65002"},"bgp-neighbor":["10.123.9.4","10.123.9.3"]}]},"operation":"PUT"}]
  
  for input in workflow_input:
    store = input.get("store")
    entity = input.get("entity").toString().replace('\"','')
    path = json.loads(input.get("path").toString())
    yang_module = data_utils.get_dict_top_key(path).split(":")[0]
    config_type = data_utils.get_dict_deepest_key(path)
    input_operation = input.get("operation").toString().replace('\"','')
    data_from_NB = json.loads(input.get("data").toString())
    
    # Log variables:
    logger.info("LSC Mount store=%s", store)
    logger.info("LSC Mount entity=%s", entity)
    logger.info(path)
    logger.info("yang_module=%s", yang_module)
    logger.info("config_type=%s", config_type)
    logger.info("Request Operation=%s", input_operation)

    #pull all the input data and perform put operations
    for s in data_from_NB["sites"]["site"]:
      logger.info ("vpn-name=%s", s["vpn-name"])
      #get the configuration params
      for n in s["nodes"]:
        index = get_index('name', n, data_from_NB["devices"]) 
        d = data_from_NB["devices"][index]
        if index != -1:
          sbi_data = {
                       "site": {
                         "vpn-name": s["vpn-name"],
                         "device-id": n
                       },
                       "devices": {
                         "vlan": {},
                         "routing-instance":{},
                         "bgp":{}
                       }
                     }
 
          if "vlan" in d:
            in_version  = "1.0"
            out_version = "1.0" 
            for v in d["vlan"]:
              v["interface"] = urllib.quote_plus(v["interface"])
              vlan_unit_url = config_url + junos_mount.format(n) + junos_inf.format(v["interface"]) + junos_unit.format(v["unit"])
              #do VLAN translation and fire http on LSC
              if "virtual" not in v:
                out_version = "1.1"
              sbi_data["devices"]["routing-instance"] = {}
              sbi_data["devices"]["vlan"]= v
              # Perform nbi to sbi translation and process result:
              sbi_requests = lsm_1.plastic_translate(vlan_in_map, junos_vlan_map, sbi_data, in_version, in_type, out_version, out_type)
              #inmarsat specific action
              if "role" in d and "MMP" in d["role"]: #set two extra params TODO need to think how to see this two params
                sbi_requests["junos-conf-interfaces:unit"][0]["family"]["inet"]["address"][0]["vrrp-group"][0]["priority"] = 200
                sbi_requests["junos-conf-interfaces:unit"][0]["family"]["inet"]["address"][0]["vrrp-group"][0]["accept-data"] = "" 
              #end
              if "vrrp-group" in sbi_requests["junos-conf-interfaces:unit"][0]["family"]["inet"]["address"][0]: 
                sr = sbi_requests
                ainf = sr["junos-conf-interfaces:unit"][0]["family"]["inet"]["address"][0]["vrrp-group"][0]["vrrp-inherit-from"]["active-interface"]
                agrp = sr["junos-conf-interfaces:unit"][0]["family"]["inet"]["address"][0]["vrrp-group"][0]["vrrp-inherit-from"]["active-group"]
                if (ainf is None or not ainf.strip() or ainf.isspace()) and (agrp is None or not agrp.strip() or agrp.isspace()):
                  del sbi_requests["junos-conf-interfaces:unit"][0]["family"]["inet"]["address"][0]["vrrp-group"][0]["vrrp-inherit-from"]
              
              if provision_operation == dc.PROVISION_UPDATE:
                logger.info("payload={0}".format(json.dumps(sbi_requests)))
                response = controller_1.http_put(vlan_unit_url, json.dumps(sbi_requests))
                if response is not None:
                  logger.info(response.status_code)
                  if response.status_code == 201 or response.status_code == 200:
                    logger.info("Setting VLAN Result as Success")
                    result["success"] = True
                  else:
                    logger.info("Setting VLAN Result as error:{0},{1}".format(response.reason,vlan_unit_url))
                    logger.info(response)
                    result["success"] = False
                else:
                  logger.info("VLAN Response error: request timout or connection error.")
                  result["success"] = False                 
              else:
                logger.info("Setting TEST Result as Success\nURL=%s\nData=%s",vlan_unit_url,sbi_requests)
                result["success"] = True
          if "routing-instance" in d:
            in_version  = "1.0"
            out_version = "1.0"
            vpn_vrf_url = config_url + junos_mount.format(n) + junos_vrfs + junos_vrf_instance.format(s["vpn-name"])
            #do VRF translation and fire http on LSC
            sbi_data["devices"]["vlan"] = {}
            sbi_data["devices"]["routing-instance"] = d["routing-instance"]
            if "bgp" in d:
              sbi_data["devices"]["bgp"] = d["bgp"]
              if "external" in d["bgp"]["type"]:
                out_version = 1.1
              else:
                out_version = 1.0
            #else: return error.  
            sbi_requests = lsm_1.plastic_translate(vpn_in_map, junos_vpn_map, sbi_data, in_version, in_type, out_version, out_type)
            if "peer-as" in sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]["group"][0]:
              pasn =  sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]["group"][0]["peer-as"] 
              logger.info("peer-as number={0}".format(pasn))
              if pasn is None or not pasn.strip() or pasn.isspace():
                #TODO mark error and return
                del sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]["group"][0]["peer-as"]
            if "local-as" in sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]:
              if "as-number" in sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]["local-as"]:
                lasn = sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]["local-as"]["as-number"] 
                logger.info("local-as number={0}".format(lasn))
                if lasn is None or not lasn.strip() or lasn.isspace():
                  #TODO mark error and return
                  del  sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]["local-as"]
            #xxx do we do for all groups
            neb = sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]["group"][0]["neighbor"]
            for ne in neb:
              if "import" in ne and "" == ne["import"][0] :
                del ne["import"]
              if "export" in ne and "" == ne["export"][0] :
                del ne["export"]
            sbi_requests["junos-conf-routing-instances:instance"][0]["protocols"]["bgp"]["group"][0]["neighbor"] = neb

            if provision_operation == dc.PROVISION_UPDATE:
              logger.info("payload={0}".format(json.dumps(sbi_requests)))
              response = controller_1.http_put(vpn_vrf_url, json.dumps(sbi_requests))
              if response is not None:
                logger.info(response.status_code)
                if response.status_code == 201 or response.status_code == 200:
                  logger.info("Setting VRF Result as Success")
                  result["success"] = True
                else:
                  logger.info("Setting VRF Result as error:{0}".format(response.reason))
                  logger.info(response)
                  result["success"] = False
              else:
                logger.info("VRF Response error: request timout or connection error.")
                result["success"] = False 
            else:
              logger.info("Setting TEST Result as Success\nURL=%s\nData=%s",vpn_vrf_url,sbi_requests)
              result["success"] = True           
          #else: return error.
        else:
          result["error"] = {"Device entry with matching name not found."}
          result["success"] = False

  execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result)
  
except Exception as e:
  #logger.info('Error: %s',e)
  logger.info('Error: %s',traceback.format_exc())
  logger.info("Internal error. please check wfe logs")
  result["data"] = {"Internal error please refer logs for further details."}
  result["success"] = False
  execution.getProcessInstance().setVariable(execution.getProcessInstanceId(), result["data"])
 
