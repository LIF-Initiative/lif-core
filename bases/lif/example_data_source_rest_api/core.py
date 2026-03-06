from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from lif.auth.core import verify_token
from lif.example_data_source_service import core as service
from lif.logging import get_logger

logger = get_logger(__name__)
app = FastAPI(
    title="LIF Example Data Source REST API",
    description="Example Data Source REST API for the LIF ecosystem",
    version="1.0.0",
)

header_scheme = APIKeyHeader(name="x-key")
logger.info(header_scheme)


def require_api_key(key: str = Depends(header_scheme)) -> str:
    """
    Extracts x-key header then verifies the token.
    """
    verify_token(key)
    return key


authenticated = APIRouter(dependencies=[Depends(require_api_key)])


@app.get("/health")
async def health_check():
    return {"status": "ok"}


r1_demo_data = {
    "100001": {
        "person": {
            "id": "100001",
            "employment": {
                "preferences": {
                    "id": "employment-preferences-100001-001",
                    "preferred_org_types": ["Public Sector", "Private Sector"],
                    "preferred_org_names": ["Government Agencies", "Technology Companies"],
                }
            },
        }
    },
    "100002": {
        "person": {
            "id": "100002",
            "employment": {
                "preferences": {
                    "id": "employment-preferences-100002-001",
                    "preferred_org_types": ["Non-Profit"],
                    "preferred_org_names": ["Healthcare Organizations", "Community Services"],
                }
            },
        }
    },
    "100003": {
        "person": {
            "id": "100003",
            "employment": {
                "preferences": {
                    "id": "employment-preferences-100003-001",
                    "preferred_org_types": ["Private Sector"],
                    "preferred_org_names": ["Corporate Partners", "Technology Companies"],
                }
            },
        }
    },
    "100004": {
        "person": {
            "id": "100004",
            "employment": {
                "preferences": {
                    "id": "employment-preferences-100004-001",
                    "preferred_org_types": ["Public Sector"],
                    "preferred_org_names": ["Government Agencies", "Educational Institutions"],
                }
            },
        }
    },
    "100005": {
        "person": {
            "id": "100005",
            "employment": {
                "preferences": {
                    "id": "employment-preferences-100005-001",
                    "preferred_org_types": ["Non-Profit", "Private Sector"],
                    "preferred_org_names": ["Healthcare Organizations", "Research Institutions"],
                }
            },
        }
    },
    "100006": {
        "person": {
            "id": "100006",
            "employment": {
                "preferences": {
                    "id": "employment-preferences-100006-001",
                    "preferred_org_types": ["Non-Profit", "Public Sector"],
                    "preferred_org_names": ["Community Services", "Government Agencies"],
                }
            },
        }
    },
}


@authenticated.get("/r1-demo/users/{user_id}")
def r1_demo_get_user(user_id: str) -> dict:
    logger.info("The Example Data Source REST API r1_demo_get_user endpoint was called for the user: %s", user_id)
    if user_id in r1_demo_data:
        return r1_demo_data[user_id]
    else:
        raise HTTPException(status_code=404, detail="User not found")


@authenticated.get("/users/{user_id}")
def get_user(user_id: int) -> dict:
    logger.info("The Example Data Source REST API get_user endpoint was called for the user: %s", user_id)
    try:
        return service.user_info(user_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@authenticated.get("/users/")
def get_users(
    age_gt: Optional[int] = None,
    age_lt: Optional[int] = None,
    age: Optional[int] = None,
    name_like: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    logger.info("The Example Data Source REST API get_users endpoint was called.")
    try:
        filters: dict[str, int | str] = {}
        if age_gt is not None:
            filters["age_gt"] = age_gt
        if age_lt is not None:
            filters["age_lt"] = age_lt
        if age is not None:
            filters["age"] = age
        if name_like is not None:
            filters["name_like"] = name_like
        if name is not None:
            filters["name"] = name
        answer = {"results": service.users_info_filtered(filters)}
        return answer
    except Exception as error:
        logger.info("Error: " + str(error))
        raise HTTPException(status_code=500, detail=str(error))


@authenticated.get("/students/")
def get_students(
    age_gt: Optional[int] = None,
    age_lt: Optional[int] = None,
    age: Optional[int] = None,
    name_like: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    logger.info("The Example Data Source REST API get_students endpoint was called.")
    try:
        filters: dict[str, int | str] = {"role": "student"}
        if age_gt is not None:
            filters["age_gt"] = age_gt
        if age_lt is not None:
            filters["age_lt"] = age_lt
        if age is not None:
            filters["age"] = age
        if name_like is not None:
            filters["name_like"] = name_like
        if name is not None:
            filters["name"] = name
        logger.info("Filters: " + str(filters))
        answer = {"results": service.users_info_filtered(filters)}
        return answer
    except Exception as error:
        logger.info("Error: " + str(error))
        raise HTTPException(status_code=500, detail=str(error))


@authenticated.get("/teachers/")
def get_teachers(
    age_gt: Optional[int] = None,
    age_lt: Optional[int] = None,
    age: Optional[int] = None,
    name_like: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    logger.info("The Example Data Source REST API get_teachers endpoint was called.")
    try:
        filters: dict[str, int | str] = {"role": "teacher"}
        if age_gt is not None:
            filters["age_gt"] = age_gt
        if age_lt is not None:
            filters["age_lt"] = age_lt
        if age is not None:
            filters["age"] = age
        if name_like is not None:
            filters["name_like"] = name_like
        if name is not None:
            filters["name"] = name
        answer = {"results": service.users_info_filtered(filters)}
        return answer
    except Exception as error:
        logger.info("Error: " + str(error))
        raise HTTPException(status_code=500, detail=str(error))


@authenticated.get("/users/{user_id}/courses")
def get_course(user_id: int) -> dict:
    try:
        return service.courses_info(None)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@authenticated.get("/users/{user_id}/courses/{course_id}")
def get_courses(user_id: int, course_id: Optional[int] = None) -> dict:
    if course_id is None:
        logger.info("The Example Data Source REST API courses endpoint was called")
    else:
        logger.info("The Example Data Source REST API courses endpoint was called for the course_id: %s", course_id)
    try:
        return service.courses_info(course_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@authenticated.get("/ob3clr2/{user_id}")
def get_ob3clr2_data(user_id: Optional[int] = None) -> dict:
    return {
        "profile": [
            {
                "@context": ["https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json"],
                "id": "https://someenterprisehrcompany.com/people/123456",
                "type": ["Profile"],
                "name": "Some Enterprise HR Company",
                "url": "https://www.linkedin.com/company/someenterprisehrcompany",
                "phone": "+1-212-555-8271",
                "description": "Some enterprise HR company",
                "email": "info@SomeEnterpriseHRCompany.com",
                "address": {
                    "type": ["Address"],
                    "addressCountry": "United States",
                    "addressCountryCode": "US",
                    "addressRegion": "New York",
                    "addressLocality": "New York",
                    "streetAddress": "123 Main Street",
                    "postOfficeBoxNumber": "456",
                    "postalCode": "12345",
                    "geo": {"type": ["GeoCoordinates"], "latitude": 41, "longitude": 74},
                },
                "otherIdentifier": {
                    "type": ["IdentifierEntry"],
                    "identifier": "123456789",
                    "identifierType": "ext:test",
                },
                "familyName": "Rodrìguez",
                "givenName": "Maria",
                "additionalName": "Gloria",
                "honorificPrefix": "Ms",
                "honorificSuffix": "Ph.D",
                "dateOfBirth": "1966-01-23",
            }
        ]
    }


@authenticated.get("/lif1/{user_id}")
def get_lif1_data(user_id: Optional[int] = None) -> dict:
    return {
        "Person": [
            {
                "Identifier": [
                    {
                        "informationSourceId": "stateu_ob2_adapter",
                        "personIdentifier": "sha256$ae8b1233df04529ee04532708135e7f54704a2e6bb74b272916d6178ffbaae0d",
                        "personIdentifierType": [
                            "https://openbadgespec.org/extensions/recipientProfile/context.json",
                            "Extension",
                            "extensions:RecipientProfile",
                        ],
                        "personSystem": "OpenBadges",
                        "personVerification": "",
                    }
                ],
                "Name": [{"firstName": "Jane", "informationSourceId": "stateu_ob2_adapter", "lastName": "Smith"}],
                "CredentialAward": [
                    {
                        "revoked": "False",
                        "uri": "https://api.badgr.io/public/assertions/1EfDfvXaQZC0OzrBD5pL5g",
                        "verificationType": "HostedBadge",
                    }
                ],
                "Organization": [{}],
            }
        ]
    }


@authenticated.get("/campusapi/{user_id}")
def get_campusapi_data(user_id: Optional[int] = None) -> JSONResponse:
    data = {
        "id": "person:1@Scott",
        "genusType": "genera:urn%3aosid%3aokapia.net%3atypes%3agenera%3apersonnel%3aPerson%3aStudent@okapai.net",
        "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/persons/person:1@Scott",
        "displayName": "Ramirez, Madeline",
        "description": "",
        "salutation": "Miss",
        "givenName": "Madeline",
        "preferredName": "",
        "surname": "Ramirez",
        "generationQualifier": "",
        "birthDate": "1998-05-06",
        "deathDate": None,
        "institutionalIdentifier": "",
        "forenameAliases": [],
        "middleNames": [],
        "surnameAliases": [],
        "courseEntries": [
            {
                "displayName": "CRMJ 150C",
                "description": "in program : 1 term : 201820 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:1@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:1@Scott",
                "startDate": "2018-01-16",
                "endDate": "2018-05-04",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:6244@Scott",
                "termId": "term:240@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:6244@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:6244@Scott",
                    "displayName": "Criminology",
                    "description": "Criminology. This course is a detailed analysis of the development of criminological theory, embracing the contributing disciplines of biology, psychology, sociology, political science and integrated theory combining those disciplines. Attention is also paid to the offender/victim relationship.  ",
                    "title": "Criminology ",
                    "number": "CRMJ 150C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1153@Scott"],
                    "creditIds": ["grade:3@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5CRJ@ccsnh",
                            "description": "Criminal Justice",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1153@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1153@Scott",
                            "displayLabel": "5CRJ: Criminal Justice",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:240@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:240@Scott",
                    "displayName": "Spring 2018",
                    "description": "Spring 2018",
                    "displayLabel": "201820",
                    "openDate": "2018-01-16",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2018-05-04",
                },
            },
            {
                "displayName": "PSYC 105C",
                "description": "in program : 1 term : 201820 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:2@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:2@Scott",
                "startDate": "2018-01-16",
                "endDate": "2018-05-04",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:2933@Scott",
                "termId": "term:240@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:2933@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:2933@Scott",
                    "displayName": "Introduction to Psychology",
                    "description": "Introduction to Psychology. An introductory college course in psychology which focuses on the fundamental facts and principles of psychology within the broader context of contemporary personal and social concerns. Topics may include the historical development of the discipline, scientific methodology, human development, motivational theory, consciousness, sensation and perception, learning, thinking, memory, emotions, biological basis of behavior, personality theory, psychopathology, sexuality, and measurements and statistics. Available in Honors format.  ",
                    "title": "Introduction to Psychology ",
                    "number": "PSYC 105C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1190@Scott"],
                    "creditIds": ["grade:0@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5SBS@ccsnh",
                            "description": "Social Sciences",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1190@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1190@Scott",
                            "displayLabel": "5SBS: Social Sciences",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:240@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:240@Scott",
                    "displayName": "Spring 2018",
                    "description": "Spring 2018",
                    "displayLabel": "201820",
                    "openDate": "2018-01-16",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2018-05-04",
                },
            },
            {
                "displayName": "LIB 104W",
                "description": "in program : 1 term : 201820 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:3@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:3@Scott",
                "startDate": "2018-01-16",
                "endDate": "2018-05-04",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:2224@Scott",
                "termId": "term:240@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:2224@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:2224@Scott",
                    "displayName": "Intro to Technical Services",
                    "description": "Intro to Technical Services. Introduction to Technical Services introduces students to the elements of technical services with print and non-print items, including selection, acquisitions, assessment, preservation, review sources, and collection development and management. The course also examines current trends and issues as they relate to these services.  ",
                    "title": "Intro to Technical Services ",
                    "number": "LIB 104W",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:919@Scott", "Organization:26@Scott"],
                    "creditIds": ["grade:3@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:WM@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:A@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-7LTP@ccsnh",
                            "description": "Library Tech",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:919@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:919@Scott",
                            "displayLabel": "7LTP: Library Tech",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DIVS-WMCC@ccsnh",
                            "description": "White Mountains",
                            "genusType": "Organization:DIVISION@institution",
                            "id": "Organization:26@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:26@Scott",
                            "displayLabel": "WMCC: White Mountains",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:240@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:240@Scott",
                    "displayName": "Spring 2018",
                    "description": "Spring 2018",
                    "displayLabel": "201820",
                    "openDate": "2018-01-16",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2018-05-04",
                },
            },
            {
                "displayName": "ENGL 101C",
                "description": "in program : 1 term : 201820 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:4@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:4@Scott",
                "startDate": "2018-01-16",
                "endDate": "2018-05-04",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:5473@Scott",
                "termId": "term:240@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:5473@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:5473@Scott",
                    "displayName": "English Composition",
                    "description": "English Composition. Required of all first-year students and designed to teach students to write clear, vigorous prose, this course takes students through all stages of the writing process. Essay topics range from personal narratives to logical arguments. All students learn the resources of the NHTI library and write at least one documented research paper. Available in Honors format. Available in Honors format.  ",
                    "title": "English Composition ",
                    "number": "ENGL 101C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1160@Scott"],
                    "creditIds": ["grade:0@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5EGL@ccsnh",
                            "description": "English",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1160@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1160@Scott",
                            "displayLabel": "5EGL: English",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:240@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:240@Scott",
                    "displayName": "Spring 2018",
                    "description": "Spring 2018",
                    "displayLabel": "201820",
                    "openDate": "2018-01-16",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2018-05-04",
                },
            },
            {
                "displayName": "HIST 121C",
                "description": "in program : 2 term : 201910 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:3964@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:3964@Scott",
                "startDate": "2018-08-27",
                "endDate": "2018-12-14",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:1995@Scott",
                "termId": "term:241@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:1995@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:1995@Scott",
                    "displayName": "U.S. History 1870-Present",
                    "description": "U.S. History 1870-Present. A course which explores the critical historic events and forces that have interacted to shape life in the U.S. Topics will include: the Industrial Revolution, World Wars, the Cold War, the role of the U.S. as a world power, social revolutions, the Great Depression, and the workings of democracy within the republic.  ",
                    "title": "U.S. History 1870-Present ",
                    "number": "HIST 121C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1190@Scott"],
                    "creditIds": ["grade:0@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5SBS@ccsnh",
                            "description": "Social Sciences",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1190@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1190@Scott",
                            "displayLabel": "5SBS: Social Sciences",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:241@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:241@Scott",
                    "displayName": "Fall 2018",
                    "description": "Fall 2018",
                    "displayLabel": "201910",
                    "openDate": "2018-08-27",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2018-12-14",
                },
            },
            {
                "displayName": "PHIL 242C",
                "description": "in program : 2 term : 201910 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:3965@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:3965@Scott",
                "startDate": "2018-08-27",
                "endDate": "2018-12-14",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:3482@Scott",
                "termId": "term:241@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:3482@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:3482@Scott",
                    "displayName": "Contemporary Ethical Issues",
                    "description": "Contemporary Ethical Issues. This course is a philosophical examination of major contemporary ethical issues. Topics may include biomedical ethics, business ethics, environmental ethics, human sexuality, and ethics related to life and death decisions. The emphasis is on acquiring the philosophical skills necessary to guide self and others in the process of ethical decision making. Cases are used for study and discussion. Available in honors format.  ",
                    "title": "Contemporary Ethical Issues ",
                    "number": "PHIL 242C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1190@Scott"],
                    "creditIds": ["grade:0@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5SBS@ccsnh",
                            "description": "Social Sciences",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1190@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1190@Scott",
                            "displayLabel": "5SBS: Social Sciences",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:241@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:241@Scott",
                    "displayName": "Fall 2018",
                    "description": "Fall 2018",
                    "displayLabel": "201910",
                    "openDate": "2018-08-27",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2018-12-14",
                },
            },
            {
                "displayName": "CHEM 103C",
                "description": "in program : 2 term : 201910 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:3966@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:3966@Scott",
                "startDate": "2018-08-27",
                "endDate": "2018-12-14",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:2396@Scott",
                "termId": "term:241@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:2396@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:2396@Scott",
                    "displayName": "General Chemistry I",
                    "description": "General Chemistry I. Fundamental laws and concepts of chemistry, including elements, atomic structure, the periodic table, chemical bonding, compounds, chemical equations, and stoichiometry. Laboratories are used to reinforce concepts presented in lectures and to develop skills in scientific thought and common procedures used in chemical experimentation. With CHEM 104C, intended to provide a foundation for further study in life sciences and physical sciences. (Prerequisites: high school chemistry with lab with a grade of “C” or higher). (Pre/Corequisite: MATH 124C or higher level math or Permission of the Department Head of Natural Sciences.)  ",
                    "title": "General Chemistry I ",
                    "number": "CHEM 103C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1150@Scott"],
                    "creditIds": ["grade:0@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5BGY@ccsnh",
                            "description": "Biology & Chemistry",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1150@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1150@Scott",
                            "displayLabel": "5BGY: Biology & Chemistry",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:241@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:241@Scott",
                    "displayName": "Fall 2018",
                    "description": "Fall 2018",
                    "displayLabel": "201910",
                    "openDate": "2018-08-27",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2018-12-14",
                },
            },
            {
                "displayName": "ENGL 285C",
                "description": "in program : 2 term : 201910 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:3967@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:3967@Scott",
                "startDate": "2018-08-27",
                "endDate": "2018-12-14",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:6094@Scott",
                "termId": "term:241@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:6094@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:6094@Scott",
                    "displayName": "Literature, Technology and Culture",
                    "description": "Literature Technology Culture. This course examines the cultural implications of science and technology in the modern world. Students study a range of essays and fictional works in traditional literature, science, and science fiction, which may include such works as Frankenstein and Brave New World. (Prerequisite: Successful completion of ENGL 101C or equivalent and an introductory level literature course are highly recommended.)  ",
                    "title": "Literature Technology Culture ",
                    "number": "ENGL 285C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1160@Scott"],
                    "creditIds": ["grade:0@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5EGL@ccsnh",
                            "description": "English",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1160@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1160@Scott",
                            "displayLabel": "5EGL: English",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:241@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:241@Scott",
                    "displayName": "Fall 2018",
                    "description": "Fall 2018",
                    "displayLabel": "201910",
                    "openDate": "2018-08-27",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2018-12-14",
                },
            },
            {
                "displayName": "ARET 120C",
                "description": "in program : 3 term : 201920 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:7879@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:7879@Scott",
                "startDate": "2019-01-22",
                "endDate": "2019-05-10",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:1540@Scott",
                "termId": "term:835@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:1540@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:1540@Scott",
                    "displayName": "Materials and Methods of Construction",
                    "description": "Mtrls & Mthds of Construction. A survey of the materials used in building construction, the methods used in assembling these materials into structures, and the forces acting on structures. Included are the characteristics and properties of each material and their relative cost. Materials and methods studied include site work, concrete, masonry, metals, wood and plastics, thermal and moisture protection, doors and windows, and finishes.  ",
                    "title": "Mtrls & Mthds of Construction ",
                    "number": "ARET 120C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1147@Scott"],
                    "creditIds": ["grade:0@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5AET@ccsnh",
                            "description": "Architectural Engineering Tech",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1147@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1147@Scott",
                            "displayLabel": "5AET: Architectural Engineering Tech",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:835@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:835@Scott",
                    "displayName": "Spring 2019",
                    "description": "Spring 2019",
                    "displayLabel": "201920",
                    "openDate": "2019-01-22",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2019-05-10",
                },
            },
            {
                "displayName": "NURS 115C",
                "description": "in program : 3 term : 201920 program  :5LIBA-AA",
                "genusType": "CourseEntry:audit@institution",
                "id": "courseEntry:7880@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chrnoicle/course-entries/courseEntry:7880@Scott",
                "startDate": "2019-01-22",
                "endDate": "2019-05-10",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "courseId": "Course:1899@Scott",
                "termId": "term:835@Scott",
                "complete": False,
                "creditScaleId": None,
                "creditsEarned": None,
                "gradeId": None,
                "scoreScaleId": None,
                "score": None,
                "course": {
                    "id": "Course:1899@Scott",
                    "genusType": "Course:CREDIT@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/courses/Course:1899@Scott",
                    "displayName": "Nursing I",
                    "description": "Nursing I. Nursing I introduces the student to the role of the associate degree nurse and the concepts of nursing knowledge and caring within the Self-Care Framework. The emphasis of the course is on assessment of the Universal Self-Care Requirements, which include air, food, activity and rest, elimination, water, solitude and social interaction. Promotion of normalcy and prevention of hazards will be addressed within the Universal Self-Care Requirements. The focus is on the use of educative/supportive nursing system and effective therapeutic communication to care for patients with selected self-care deficits. Professional, ethical and legal standards of nursing practice are introduced to provide culturally-sensitive nursing care. Opportunities for application of nursing knowledge to clinical practice are provided through Clinical Resource Center experiences and patient care assignments in various settings. To facilitate the teaching/learning process, ongoing evaluations occur through interactions between student and faculty. (Co-requisites: BIOL 195C, ENGL 101C, and PSYC 105C) Clinical sites are in medical/surgical settings.  ",
                    "title": "Nursing I ",
                    "number": "NURS 115C",
                    "prerequisitesInfo": " ",
                    "sponsorIds": ["Organization:12@Scott", "Organization:1179@Scott"],
                    "creditIds": ["grade:0@ccsnh"],
                    "prerequisiteIds": [],
                    "levelIds": ["grade:TI@ccsnh"],
                    "gradingOptionIds": ["gradeSystem:E@ccsnh", "gradeSystem:N@ccsnh", "gradeSystem:T@ccsnh"],
                    "learningObjectiveIds": [],
                    "sponsors": [
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:DEPT-5NUR@ccsnh",
                            "description": "Nursing",
                            "genusType": "Organization:DEPARTMENT@institution",
                            "id": "Organization:1179@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:1179@Scott",
                            "displayLabel": "5NUR: Nursing",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:835@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:835@Scott",
                    "displayName": "Spring 2019",
                    "description": "Spring 2019",
                    "displayLabel": "201920",
                    "openDate": "2019-01-22",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2019-05-10",
                },
            },
        ],
        "programEntries": [
            {
                "displayName": "5LIBA-AA: Liberal Arts-AA - Fall 2017",
                "description": "Liberal Arts-AA. The Liberal Arts curriculum provides students with broad general knowledge and skills in the arts and sciences. It is designed to provide a basis for transfer to four-year liberal arts programs at other colleges and universities. In addition, the Liberal Arts program provides a starting point for undecided students, as well as those planning to complete prerequisite courses to transfer into Engineering Technology, Math, Biology, Health Science, Environmental Science, or Accounting at NHTI. The program is flexible - students select courses based on the requirements of the program or college to which they plan to transfer   = Fall 2017",
                "genusType": "ProgramEntry:TW@institution",
                "id": "programEntry:1@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chronicle/program-entries/programEntry:1@Scott",
                "startDate": "2017-08-28",
                "endDate": "2017-12-15",
                "endReasonId": None,
                "admissionDate": "2017-08-28",
                "studentId": "person:1@Scott",
                "programId": "Program:3133@Scott",
                "complete": True,
                "termId": "term:1469@Scott",
                "creditScaleId": "CreditScale:AA@Ods",
                "creditsEarned": None,
                "gpaScaleId": None,
                "gpa": None,
                "program": {
                    "id": "Program:3133@Scott",
                    "genusType": "Program:institution.program@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/program/programs/Program:3133@Scott",
                    "displayName": "Liberal Arts-AA",
                    "description": "Liberal Arts-AA. The Liberal Arts curriculum provides students with broad general knowledge and skills in the arts and sciences. It is designed to provide a basis for transfer to four-year liberal arts programs at other colleges and universities. In addition, the Liberal Arts program provides a starting point for undecided students, as well as those planning to complete prerequisite courses to transfer into Engineering Technology, Math, Biology, Health Science, Environmental Science, or Accounting at NHTI. The program is flexible - students select courses based on the requirements of the program or college to which they plan to transfer  ",
                    "title": "Liberal Arts-AA ",
                    "number": "5LIBA-AA",
                    "completionRequirementsInfo": None,
                    "sponsorIds": ["Organization:6@Scott", "Organization:12@Scott", "Organization:299@Scott"],
                    "completionRequirementIds": [],
                    "credentialIds": ["Credential:AA@ccsnh"],
                    "sponsors": [
                        {
                            "displayName": "Organization:CAMP-NHT@ccsnh",
                            "description": "NHTI",
                            "genusType": "Organization:CAMPUS@institution",
                            "id": "Organization:6@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:6@Scott",
                            "displayLabel": "NHT: NHTI",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:COLL-TE@ccsnh",
                            "description": "Technical Education",
                            "genusType": "Organization:COLLEGE@institution",
                            "id": "Organization:12@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:12@Scott",
                            "displayLabel": "TE: Technical Education",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                        {
                            "displayName": "Organization:MAJR-LIBA@ccsnh",
                            "description": "Liberal Arts",
                            "genusType": "Organization:MAJOR@institution",
                            "id": "Organization:299@Scott",
                            "uri": "https://demo.dxtera.org/campus-api-rest/api/personnel/organizations/Organization:299@Scott",
                            "displayLabel": "LIBA: Liberal Arts",
                            "startDate": "undefined",
                            "endDate": "undefined",
                        },
                    ],
                },
                "term": {
                    "id": "term:1469@Scott",
                    "genusType": "Term:TERM@institution",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/course/terms/term:1469@Scott",
                    "displayName": "Fall 2017",
                    "description": "Fall 2017",
                    "displayLabel": "201810",
                    "openDate": "2017-08-28",
                    "registrationStart": None,
                    "registrationEnd": None,
                    "classesStart": None,
                    "classesEnd": None,
                    "addDate": None,
                    "dropDate": None,
                    "finalExamStart": None,
                    "finalExamEnd": None,
                    "closeDate": "2017-12-15",
                },
            }
        ],
        "credentialEntries": [
            {
                "displayName": "person:1@Scott",
                "description": "5LIBA-AA",
                "genusType": "CredentialEntry:CredentialEntry-AW@institution",
                "id": "credentialEntry:1@Scott",
                "uri": "https://demo.dxtera.org/campus-api-rest/api/chronicle/credential-entries/credentialEntry:1@Scott",
                "startDate": "2020-05-08",
                "endDate": "2021-05-08",
                "endReasonId": None,
                "studentId": "person:1@Scott",
                "credentialId": "credential:2@Scott",
                "dateAwarded": "2021-05-08",
                "programId": "Program:3133@Scott",
                "credential": {
                    "id": "credential:2@Scott",
                    "genusType": "genera:urn%3aosid%3aokapia.net%3atypes%3agenera%3acourse%3aCredential@okapia.net",
                    "uri": "https://demo.dxtera.org/campus-api-rest/api/program/credentials/credential:2@Scott",
                    "displayName": "AA",
                    "description": "",
                    "lifetime": "∞",
                },
            }
        ],
    }

    return JSONResponse(content=data)


# Needs to happen after endpoints are defined
app.include_router(authenticated)
