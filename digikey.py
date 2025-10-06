import requests
import pandas as pd # type: ignore
from requests.auth import HTTPBasicAuth

import re
import ast
import math



def Web_inteface(lis1):
    try:
        Li=[p.strip() for p in lis1.split(',') if p.strip()]
        fin_11=[]
        client_id = "0dhv3AZgnR9XJnjvVs8RMwI5c2aWbUNA"
        client_secret = "bKXnVOBACsXedDa5"
        auth_url = "https://api.digikey.com/v1/oauth2/token"
        data = {
            "grant_type": "client_credentials"
        }
        token_response = requests.post ( auth_url, data =data, auth=HTTPBasicAuth(client_id, client_secret ) )
        if token_response.status_code == 200:
            access_token= token_response.json()["access_token"]
            print("Access token received.")
        else:
            print("Token error:", token_response.text)
            access_token = None

            #input("Enter the type of component(Resistor capacito/transistor..):")

            #part_list = [ "SLA7067MRPLF2104", "T867S128FTG(O, EL)", "DRV8818PWPR", "DRV8311HRRWR"]
        part_list=Li
        if access_token:
            headers = {

                    "Authorization": f"Bearer {access_token}",

                    "X-DIGIKEY-Client-Id": client_id,

                    "Content-Type": "application/json",

                    "Accept": "application/json"
            }

            product_url = "https://api.digikey.com/products/v4/search/keyword" #part_number = "GCM1885C1H180JA16D"

            miss=[]
            for part in range(len(part_list)):
                body = {

                   "keywords": part_list[part],
                    "recordCount": 1
                }

                response = requests.post(product_url, headers=headers, json=body)

                specs={"Part Number": part_list[part].upper()}

                if response.status_code == 200:

                    result = response.json()                  

                    if result['Products']==[]:
                        miss.append
                    else:

                        pr=result['Products'] [0] ["Parameters"]

                        specs["Mfr"]=result['Products'] [0] ['Manufacturer'] ['Name']

                        specs ["Part Status"]=result['Products'] [0] ['ProductStatus'] ['Status']

                        for e in pr:

                            specs [e['ParameterText']]=e["ValueText"]

                        fin_11.append(specs)

                else:

                    print("Search error:", response.text)

        p_1 = [pd.DataFrame(d.items(), columns=["Attribute", "Value"]) for d in fin_11 ] 
        
        templ=[" consider important parameter along with part status"]
        res=pd.concat(p_1,ignore_index=True)
        return res
    except Exception as e:
        print("Error:",e)
        return "ERRor :"+str(e)
import gradio as gr

iface = gr. Interface(
fn=Web_inteface,
inputs=gr.Textbox(label="Enter Part Numbers (comma separated)", lines=4, placeholder="e.g. ABC123, XYZ456"),
#outputs=gr.File(label="Download Excel Comparison"),
outputs="dataframe",
title="Electronic Parts Comparison Tool",
description="Enter a list of part numbers to get their alternate comparison in Excel format."

)

iface.launch (share=True)