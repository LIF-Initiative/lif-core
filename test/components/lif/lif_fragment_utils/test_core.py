import json

from lif.datatypes.core import LIFFragment
from lif.lif_fragment_utils import core


person_alan_json = """{
    "person": [
        {
            "name": [
                {
                  "lastName": "Doe",
                  "firstName": "John"
                }
            ],
            "identifier": [
                {
                    "identifier": "12345",
                    "identifier_type": "School-assigned number"
                }
            ],
            "employmentLearningExperience": [
                {
                    "name": "Compliance Manager",
                    "position": [
                        {
                            "description": "Oversee the compliance department to ensure adherence to industry regulations and company policies."
                        }
                    ],
                    "startDate": "2007-06"
                }
            ],
            "positionPreferences": [
                {
                    "travel": [
                        {
                            "percentage": 25.0,
                            "willingToTravelIndicator": true
                        }
                    ]
                }
            ]
        }
    ]
}"""
person_alan_dict = json.loads(person_alan_json)


def test_adjust_lif_fragments_for_initial_orchestrator_simplification():
    lif_fragments = [
        LIFFragment(fragment_path="person.all", fragment=[person_alan_dict]),
        LIFFragment(fragment_path="person.address", fragment=[{"city": "Seattle", "state": "WA"}]),
    ]
    desired_fragment_paths = ["person.employmentLearningExperience", "person.positionPreferences"]

    adjusted_fragments = core.adjust_lif_fragments_for_initial_orchestrator_simplification(
        lif_fragments, desired_fragment_paths
    )

    assert len(adjusted_fragments) == 3
    assert adjusted_fragments[0].fragment_path == "person.employmentLearningExperience"
    assert adjusted_fragments[0].fragment == person_alan_dict["person"][0]["employmentLearningExperience"]
    assert adjusted_fragments[1].fragment_path == "person.positionPreferences"
    assert adjusted_fragments[1].fragment == person_alan_dict["person"][0]["positionPreferences"]
    assert adjusted_fragments[2].fragment_path == "person.address"
