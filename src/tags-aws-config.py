import json,logging,os,boto3
from botocore.exceptions import ClientError
client_ssm = boto3.client('ssm')
client_tags = boto3.client('resourcegroupstaggingapi')
client_config = boto3.client('config')
logging.basicConfig(format='%(asctime)s [%(levelname)+8s]%(module)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, os.getenv('LOG_LEVEL', 'INFO')))
prefix_parameter = os.getenv('PREFIX_PARAMETER')
config_rule_name = os.getenv('CONFIG_RULE_NAME') 


def describe_parameters():
    logger.info('describing paramerter store')
    try:
        response = client_ssm.describe_parameters(
            ParameterFilters=[{'Key' : 'Name', 'Values' : [prefix_parameter], 'Option': 'BeginsWith'} ]
            )
        logger.info('Parmaeters stores: %s ' % response['Parameters'])
        return response['Parameters']
    
    except ClientError as e:
        logger.error('Failed to describe parameters with prefix %s: Error: %s' % (prefix_parameter,e))


def describe_current_tags(resourceId,resourceType):
    try:
        logger.info('Getting information tags for %s , %s ' % (resourceId, resourceType))
        response = client_config.get_resource_config_history(
            resourceType=resourceType,
            resourceId=resourceId)
        logger.info('current tags applied to %s are %s ' % (resourceId, str(response['configurationItems'][0]['tags'])))
        return response['configurationItems'][0]['tags']
    except ClientError as e:
        logger.error('Failed to describe parameters with prefix %s: Error: %s' % (prefix_parameter,e))


def create_parameter_dict(parameter_list):
    dict_tags = {}
    for i in parameter_list:
        parameter_name = i['Name']
        key_parameter_name = parameter_name.split(prefix_parameter)[1]
        try: 
            dict_tags[key_parameter_name] = client_ssm.get_parameter(Name=i['Name'])['Parameter']['Value']
        except ClientError as e:
            logger.error('Failed to get parameter value from  %s: Error: %s' % (i,e))
            logger.error('This is the dict_tags value %s' % (json.dumps(dict_tags)))
    logger.info('This is the dict_tags value %s' % (json.dumps(dict_tags)))
    return dict_tags


def tag_resources(dict_tags, resource_arn,configuration_item,current_tags):
    
    temp_list = []

    if configuration_item['configurationItemStatus'] == "ResourceDeleted":
        logger.info('The resource was deleted and validation configuration is not applicable')
        return {
            "compliance_type": "NOT_APPLICABLE",
            "annotation": "The configurationItem was deleted and therefore cannot be validated"
        }
    
    for key in dict_tags:
        if key in current_tags:
            if current_tags[key] != dict_tags[key]:
                temp_list.append(key)
        else:
            temp_list.append(key)
    
    
    if len(temp_list) > 0:
        logger.info('Current tags are not compliant for %s ' % str(temp_list))
        logger.info('Tagging resource %s ' % resource_arn)
        
        try:
            response = client_tags.tag_resources(
                ResourceARNList=[
                    resource_arn,
                ],
                Tags=dict_tags
            )
            if response.get('FailedResourcesMap'):
                logger.error('Failed to Tag resource with error %s ' % (response['FailedResourcesMap']))
                return {
                    "compliance_type": "NON_COMPLIANT",
                    "annotation": "it was not possible to update  tags"
                }
            else:
                logger.info('Tags added')
                logger.info(json.dumps(response))
            return {
                "compliance_type": "COMPLIANT",
                "annotation": "Tags Updated"
            }            
        except ClientError as e:
            logger.error('Failed to update tags %s: Error: %s' % (json.dumps(dict_tags),e))
            return {
                "compliance_type": "NON_COMPLIANT",
                "annotation": "it was not possible to update  tags"
            }
        
    else:
        logger.info('Tags are up to date, nothing to do')
        return {
            "compliance_type": "COMPLIANT",
            "annotation": "Tags compliant"
        }                    

def lambda_handler(event, context):
    logger.info('this is the json event %s ' % json.dumps(event))
    if  event.get('source') and event['source'] == 'aws.ssm':
        logger.info('Paramter Store Changed, starting re-evaluation of Config Rule for all Resources ')
        try: 
            response = client_config.start_config_rules_evaluation(
            ConfigRuleNames=[
                config_rule_name
            ]
        )
            return {
                "Status": "OK"
            }
        except ClientError as e:
            logger.error('Failed to re-evaluate Config Rule with error %s' % (e))     
            return {
                "Status": "OK"
            }
    else:            
        invoking_event = json.loads(event['invokingEvent'])
        configuration_item = invoking_event['configurationItem']
        result_token = event['resultToken']
        response=json.loads(event['invokingEvent'])
        resourceId = response['configurationItem']['resourceId']
        resource_arn = response['configurationItem']['ARN']
        resourceType = response['configurationItem']['resourceType']
        parameter_list = describe_parameters()
        dict_tags = create_parameter_dict(parameter_list)
        current_tags = describe_current_tags(resourceId,resourceType)
        evaluation = tag_resources(dict_tags, resource_arn,configuration_item,current_tags)
        try:
            client_config.put_evaluations(
                Evaluations=[
                    {
                        "ComplianceResourceType":
                            configuration_item["resourceType"],
                        "ComplianceResourceId":
                            configuration_item["resourceId"],
                        "ComplianceType":
                            evaluation["compliance_type"],
                        "Annotation":
                            evaluation["annotation"],
                        "OrderingTimestamp":
                            configuration_item["configurationItemCaptureTime"]
                    },
                ],
                ResultToken=result_token
            )
            return {
                'Status' : 'OK'
            }
        except ClientError as e:
            logger.info('Cannot update config rule status of evaluation with error %s ' % (e))
            return {
                'Status : NOTOK'
            }