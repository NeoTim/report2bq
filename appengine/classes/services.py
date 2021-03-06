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

from enum import Enum
from typing import Any, Dict


class Service(Enum):
  SCHEDULER = 'scheduler'
  DV360 = 'dv360'
  CM = 'cm'
  
  def __str__(self):
    return str(self.value)


  def definition(self) -> Dict[str, Any]:
    defs = {
      'scheduler': {
        'serviceName': 'cloudscheduler',
        'version': 'v1',
      },
      'cm': {
        'serviceName': 'dfareporting',
        'version': 'v3.3',
      },
      'dv360': {
        'serviceName': 'doubleclickbidmanager',
        'version': 'v1.1'
      },
    }
    return defs.get(self.value, {})

