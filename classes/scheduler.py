"""
Copyright 2020 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

__author__ = [
    'davidharcombe@google.com (David Harcombe)'
]

import base64
import json
import logging
import os
import pprint
import random
import uuid

# Class Imports
from io import StringIO
from typing import Any, Dict, Generator, List, Mapping, Tuple

from google.cloud import scheduler as scheduler
from google.cloud.pubsub import PublisherClient
from googleapiclient.errors import HttpError

from classes.credentials import Credentials
from classes.discovery import DiscoverService
from classes.services import Service
from classes import Fetcher


class Scheduler(Fetcher):
  """Scheduler helper
  
  Handles the scheduler operations for Report2BQ

  """

  def process(self, args: Dict[str, Any]) -> str:
    logging.info(f'args: {args}')

    _action = args.get('action')
    _project = args.get('project')
    _email = args.get('email')

    _credentials = Credentials(
      email=_email,
      project=_project
    )
    
    locations = self.list_locations(credentials=_credentials, project=_project)
    _location = locations[-1]

    if _action == 'list':
      jobs = self.list_jobs(
        credentials=_credentials, 
        project=_project, location=_location, 
        email=_email)
      result = StringIO()
      result.writelines([f"{job['name']}: {job.get('description') or 'No description.'}<br/>" for job in jobs])
      return result.getvalue()

    elif _action == 'delete':
      (success, error) = self.delete_job(
        credentials=_credentials, 
        project=_project,
        location=_location,
        job_id=args.get('job_id'))

      if success:
        return 'OK'
      else:
        return f'ERROR!\n{error["error"]["message"]}'

    elif _action == 'create':
      _attrs = {
        'email': _email,
        'project': _project,
        'force': str(args.get('force')),
        'infer_schema': str(args.get('infer_schema')),
        'append': str(args.get('append')),
      }

      if args.get('minute'):
        minute = args.get('minute')
      else:
        random.seed(uuid.uuid4())
        minute = random.randrange(0, 59)

      if args.get('sa360_url'):
        product = _type = 'sa360'
        hour = args.get('hour') if args.get('hour') else '3'
        action = 'fetch'
        topic = 'report2bq-trigger'
        _attrs.update({
          'sa360_url': args.get('sa360_url'),
          'type': 'sa360',
        })

      elif args.get('adh_customer'):
        product = _type = 'adh'
        hour = args.get('hour') if args.get('hour') else '2'
        action = 'run'
        topic = 'report2bq-trigger'
        _attrs.update({
          'adh_customer': args.get('adh_customer'),
          'adh_query': args.get('adh_query'),
          'api_key': args.get('api_key'),
          'days': args.get('days'),
          'type': 'adh',
        })
      else:
        if args.get('runner'):
          hour = args.get('hour') if args.get('hour') else '1'
          action = 'run'
          topic = 'rerport_runner'
        else:
          hour = '*'
          action = 'fetch'
          topic = 'report2bq-trigger'

        if args.get('profile'):
          product = 'cm'
          _type = 'cm'
          _attrs.update({
            'profile': args.get('profile'),
            'cm_id': args.get('report_id'),
            'type': 'cm',
          })
        else:
          product = 'dv360'
          _type = 'dbm'
          _attrs.update({
            'dv360_id': args.get('report_id'),
            'type': 'dbm',
          })

      name = f"{action}-{product}-{args.get('report_id')}"
      schedule = f"{minute} {hour} * * *"

      job = { 
        'description': args.get('description'),
        'timeZone': args.get('timezone') or 'UTC',
        'api_key': args.get('api_key'),
        'name': name,
        'schedule': schedule,
        'topic': topic,
        'attributes': _attrs,
      }

      self.create_job(
        credentials=_credentials, 
        project=_project,
        location=_location,
        job=job)


  def list_locations(self, credentials: Credentials=None, project: str=None):
    service = DiscoverService.get_service(Service.SCHEDULER, credentials, api_key=os.environ['API_KEY'])
    locations_response = self.fetch(method=service.projects().locations().list, **{'name': scheduler.CloudSchedulerClient.project_path(project)})
    locations = list([ location['locationId'] for location in locations_response['locations'] ])

    return locations


  def list_jobs(self, credentials: Credentials=None, project: str=None, location: str=None, email: str=None) -> List[Dict[str, Any]]:
    """copy from one bucket to another

    This is a copy from the bucket defined in the report definition (as DV360 stores it's
    reports in GCS) into the monitored bucket for upload. It's BLAZING fast, to the extent
    that there is essentially no limit on the maximum size of a DV360 report we can handle.

    The destination file name is the report's id.
    
    Arguments:
        bucket_name {str} -- destination bucket name
        report {Dict[str, Any]} -- report definition
    """
    service = DiscoverService.get_service(Service.SCHEDULER, credentials, api_key=os.environ['API_KEY'])
    token = None
    method = service.projects().locations().jobs().list
    jobs = []

    while True:
      _kwargs = {
        'parent': scheduler.CloudSchedulerClient.location_path(project, location),
        'pageToken': token
      }

      _jobs = self.fetch(method, **_kwargs)
      jobs.extend(_jobs['jobs'] if 'jobs' in _jobs else [])

      if 'nextPageToken' not in _jobs:
        break

      token = _jobs['nextPageToken']

    if email and jobs:
      jobs = filter(
        lambda j: j.get('pubsubTarget', {}).get('attributes', {}).get('email', '') == email,
        jobs
      )
    
    return jobs


  def delete_job(self, job_id: str=None, credentials: Credentials=None, project: str=None, location: str=None) -> Tuple[bool, Dict[str, Any]]:
    service = DiscoverService.get_service(Service.SCHEDULER, credentials, api_key=os.environ['API_KEY'])
    method = service.projects().locations().jobs().delete

    try:
      method(name=scheduler.CloudSchedulerClient.job_path(project=project, location=location, job=job_id)).execute()
      return (True, None)

    except HttpError as error:
      e = json.loads(error.content)
      return (False, e)


  def create_job(self, credentials: Credentials=None, project: str=None, location: str=None, job: Dict[str, Any]=None):
    service = DiscoverService.get_service(Service.SCHEDULER, credentials, api_key=os.environ['API_KEY'])
    _method = service.projects().locations().jobs().create

    _parent = scheduler.CloudSchedulerClient.location_path(project=project, location=location)
    _target = {
      'topicName': f"projects/{project}/topics/{job.get('topic', '')}",
      # 'data': base64.b64encode(b'RUN'),
      'attributes': job.get('attributes', ''),
    }
    body: dict = {
      "name": scheduler.CloudSchedulerClient.job_path(project=project, location=location, job=job.get('name', '')),
      "description": job.get('description', ''),
      "schedule": job.get('schedule', ''),
      "timeZone": job.get('timezone', ''),
      'pubsubTarget': _target
    }

    _args = {
      'parent': _parent,
      'body': body
    }
    request = _method(**_args)
    request.execute()
