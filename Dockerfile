FROM public.ecr.aws/lambda/python:3.8

COPY solve.py segmentation.py classification.py lambda_function.py requirements.txt ./

RUN yum -y install mesa-libGL && yum clean all && rm -rf /var/cache/yum
RUN python3.8 -m pip install -r requirements.txt -t . --no-cache-dir

CMD ["lambda_function.lambda_handler"]
