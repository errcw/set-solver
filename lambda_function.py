import json

import cv2
import numpy as np

def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps('Hiiiiiiiii!')
    }
