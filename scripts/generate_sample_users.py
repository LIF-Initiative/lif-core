#!/usr/bin/env python3
"""
Script to generate additional sample user data across the 3 demo organizations.

This script generates X number of sample users across advisor-demo-org1, advisor-demo-org2,
and advisor-demo-org3, where X is configurable. Each user will be created in all 3 orgs
with appropriate org-specific information.

Usage:
    python generate_sample_users.py --num-users 5
    python generate_sample_users.py --num-users 10 --output-dir /custom/path
"""

import json
import argparse
import random
import hashlib
import uuid
import datetime
from pathlib import Path
from typing import Dict, Any

# Base directory for sample data - works from anywhere by finding the script's location
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "projects" / "mongodb" / "sample_data"

# Organization configurations
ORG_CONFIG = {
    "advisor-demo-org1": {
        "id": "Org1",
        "domain": "stateu.edu",
        "school_id_prefix": "100",
        "next_id": 1000,  # Starting ID for new users
    },
    "advisor-demo-org2": {
        "id": "Org2",
        "domain": "stateu.edu",
        "school_id_prefix": "100",
        "next_id": 2000,  # Starting ID for new users
    },
    "advisor-demo-org3": {
        "id": "Org3",
        "domain": "stateu.edu",
        "school_id_prefix": "100",
        "university_id_prefix": "SVU-202500",
        "next_id": 3000,  # Starting ID for new users
    },
}

# Sample data for generating users
FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Taylor",
    "Morgan",
    "Casey",
    "Riley",
    "Avery",
    "Quinn",
    "Blake",
    "Cameron",
    "Dana",
    "Drew",
    "Emery",
    "Finley",
    "Harper",
    "Jamie",
    "Kendall",
    "Logan",
    "Marley",
    "Nico",
    "Parker",
    "River",
    "Sage",
    "Skyler",
    "Aaron",
    "Abigail",
    "Adam",
    "Adrian",
    "Aiden",
    "Alexa",
    "Alice",
    "Amanda",
    "Amy",
    "Andrew",
    "Anna",
    "Anthony",
    "Ashley",
    "Austin",
    "Benjamin",
    "Brandon",
    "Brian",
    "Brianna",
    "Caleb",
    "Carlos",
    "Caroline",
    "Catherine",
    "Charles",
    "Charlotte",
    "Christian",
    "Christopher",
    "Claire",
    "Cole",
    "Connor",
    "Crystal",
    "Daniel",
    "David",
    "Derek",
    "Diana",
    "Diego",
    "Dylan",
    "Edward",
    "Elizabeth",
    "Emily",
    "Emma",
    "Eric",
    "Ethan",
    "Eva",
    "Gabriel",
    "Grace",
    "Hannah",
    "Ian",
    "Isaac",
    "Isabella",
    "Jack",
    "Jacob",
    "James",
    "Jason",
    "Jennifer",
    "Jessica",
    "John",
    "Jonathan",
    "Jose",
    "Joshua",
    "Julia",
    "Justin",
    "Katherine",
    "Kevin",
    "Lauren",
    "Liam",
    "Lucas",
    "Madison",
    "Marcus",
    "Maria",
    "Mark",
    "Matthew",
    "Maya",
    "Megan",
    "Michael",
    "Michelle",
    "Nathan",
    "Nicholas",
    "Nicole",
    "Noah",
    "Olivia",
    "Owen",
    "Patrick",
    "Paul",
    "Rachel",
    "Rebecca",
    "Richard",
    "Robert",
    "Ryan",
    "Samuel",
    "Sarah",
    "Sean",
    "Sophia",
    "Stephen",
    "Steven",
    "Thomas",
    "Tyler",
    "Victoria",
    "William",
    "Zachary",
    "Zoe",
    "Aria",
    "Asher",
    "Aurora",
    "Axel",
    "Bella",
    "Bryce",
    "Chloe",
    "Colton",
    "Easton",
    "Elena",
    "Eli",
    "Ella",
    "Elliott",
    "Ellie",
    "Emma",
    "Evelyn",
    "Felix",
    "Hazel",
    "Hudson",
    "Ivy",
    "Jaxon",
    "Layla",
    "Leo",
    "Lila",
    "Lincoln",
    "Luna",
    "Mason",
    "Mia",
    "Miles",
    "Nora",
    "Oliver",
    "Paisley",
    "Piper",
    "Quinn",
    "Ryder",
    "Scarlett",
    "Sebastian",
    "Stella",
    "Theodore",
    "Violet",
    "Aaliyah",
    "Adrien",
    "Aisha",
    "Alejandro",
    "Ana",
    "Andre",
    "Angelo",
    "Antonio",
    "Camila",
    "Carmen",
    "Cesar",
    "Cristian",
    "Daniela",
    "Eduardo",
    "Elena",
    "Fernando",
    "Francisco",
    "Gabriela",
    "Giovanni",
    "Gonzalo",
    "Hector",
    "Isabel",
    "Ivan",
    "Javier",
    "Jesus",
    "Joaquin",
    "Jorge",
    "Juan",
    "Julio",
    "Leonardo",
    "Luis",
    "Manuel",
    "Marco",
    "Mariana",
    "Mario",
    "Miguel",
    "Nicolas",
    "Pablo",
    "Patricia",
    "Pedro",
    "Rafael",
    "Raul",
    "Ricardo",
    "Roberto",
    "Rodrigo",
    "Rosa",
    "Salvador",
    "Santiago",
    "Sofia",
    "Teresa",
    "Valeria",
    "Vicente",
    "Xavier",
    "Ximena",
    "Yolanda",
]

LAST_NAMES = [
    "Anderson",
    "Brown",
    "Davis",
    "Garcia",
    "Johnson",
    "Jones",
    "Martinez",
    "Miller",
    "Rodriguez",
    "Smith",
    "Taylor",
    "Thomas",
    "White",
    "Williams",
    "Wilson",
    "Clark",
    "Lewis",
    "Lee",
    "Walker",
    "Hall",
    "Allen",
    "Young",
    "Hernandez",
    "King",
    "Wright",
    "Lopez",
    "Hill",
    "Scott",
    "Green",
    "Adams",
    "Baker",
    "Barnes",
    "Bell",
    "Bennett",
    "Brooks",
    "Butler",
    "Campbell",
    "Carter",
    "Collins",
    "Cook",
    "Cooper",
    "Cox",
    "Cruz",
    "Diaz",
    "Edwards",
    "Evans",
    "Fisher",
    "Flores",
    "Foster",
    "Gonzalez",
    "Gray",
    "Harris",
    "Henderson",
    "Howard",
    "Hughes",
    "Jackson",
    "James",
    "Kelly",
    "Long",
    "Moore",
    "Morgan",
    "Morris",
    "Murphy",
    "Nelson",
    "Parker",
    "Patterson",
    "Perez",
    "Perry",
    "Peterson",
    "Phillips",
    "Powell",
    "Price",
    "Ramirez",
    "Reed",
    "Reyes",
    "Richardson",
    "Rivera",
    "Roberts",
    "Robinson",
    "Rogers",
    "Ross",
    "Russell",
    "Sanchez",
    "Sanders",
    "Stewart",
    "Thompson",
    "Torres",
    "Turner",
    "Ward",
    "Washington",
    "Watson",
    "Wood",
    "Wright",
    "Abbott",
    "Archer",
    "Armstrong",
    "Barber",
    "Bishop",
    "Blacksmith",
    "Brewer",
    "Carpenter",
    "Chapman",
    "Chandler",
    "Clayton",
    "Cooper",
    "Curtis",
    "Dean",
    "Dixon",
    "Duncan",
    "Elliott",
    "Ferguson",
    "Fleming",
    "Fletcher",
    "Ford",
    "Franklin",
    "Gardner",
    "Garrett",
    "Gibson",
    "Graham",
    "Grant",
    "Griffin",
    "Hamilton",
    "Harper",
    "Harrison",
    "Hart",
    "Harvey",
    "Hayes",
    "Holmes",
    "Hunter",
    "Jordan",
    "Kennedy",
    "Knight",
    "Lane",
    "Lawrence",
    "Mason",
    "Mitchell",
    "Palmer",
    "Porter",
    "Reynolds",
    "Shaw",
    "Shepherd",
    "Simpson",
    "Stevens",
    "Sullivan",
    "Tucker",
    "Webb",
    "Wells",
    "West",
    "Wheeler",
    "Austin",
    "Boston",
    "Bristol",
    "Burton",
    "Camden",
    "Carlton",
    "Chester",
    "Churchill",
    "Cleveland",
    "Clinton",
    "Dalton",
    "Denver",
    "Dover",
    "Durham",
    "Edison",
    "Fairfax",
    "Georgetown",
    "Hampton",
    "Harrison",
    "Houston",
    "Hudson",
    "Jefferson",
    "Kingston",
    "Lancaster",
    "Lincoln",
    "Madison",
    "Marshall",
    "Montgomery",
    "Newport",
    "Newton",
    "Oxford",
    "Preston",
    "Princeton",
    "Richmond",
    "Salem",
    "Sheffield",
    "Sterling",
    "Stockton",
    "Stratford",
    "Thornton",
    "Trenton",
    "Valencia",
    "Vernon",
    "Walton",
    "Warren",
    "Webster",
    "Wellington",
    "Westbrook",
    "Rivers",
    "Woods",
    "Stone",
    "Field",
    "Brook",
    "Lake",
    "Forest",
    "Mountain",
    "Valley",
    "Meadow",
    "Grove",
    "Creek",
    "Ridge",
    "Beach",
    "Shore",
    "Ocean",
    "Storm",
    "Snow",
    "Rain",
    "Wind",
    "Star",
    "Moon",
    "Sun",
    "Rose",
    "Pine",
    "Oak",
    "Ash",
    "Birch",
    "Cedar",
    "Elm",
    "Maple",
    "Willow",
    "Blake",
    "Chase",
    "Cole",
    "Cross",
    "Drake",
    "Fox",
    "Gold",
    "Hunt",
    "Kane",
    "Knox",
    "Nash",
    "Page",
    "Pierce",
    "Quinn",
    "Reid",
    "Sage",
    "Stone",
    "Swift",
    "Vale",
    "Wade",
    "York",
    "Zane",
]

CITIES_STATES = [
    ("Salt Lake City", "Utah", "84101"),
    ("Denver", "Colorado", "80201"),
    ("Phoenix", "Arizona", "85001"),
    ("Austin", "Texas", "73301"),
    ("Atlanta", "Georgia", "30301"),
    ("Charlotte", "North Carolina", "28201"),
    ("Tampa", "Florida", "33601"),
    ("Portland", "Oregon", "97201"),
    ("Seattle", "Washington", "98101"),
    ("Minneapolis", "Minnesota", "55401"),
]

SKILLS = [
    # Core business skills
    {
        "name": "Project Management",
        "description": "Project management involves planning, organizing, and managing resources to bring about the successful completion of specific project goals and objectives.",
    },
    {
        "name": "Data Analysis",
        "description": "Data analysis involves using various techniques and methods to process, transform, and summarize data in order to extract meaningful insights and information.",
    },
    {
        "name": "Communication",
        "description": "Communication is the exchange of information between individuals through a common system of symbols, signs, or behavior.",
    },
    {
        "name": "Leadership",
        "description": "Leadership is the ability to guide, influence, and inspire others towards achieving common goals and objectives.",
    },
    {
        "name": "Problem Solving",
        "description": "Problem solving is the process of finding solutions to difficult or complex issues through systematic approaches and critical thinking.",
    },
    {
        "name": "Team Collaboration",
        "description": "Team collaboration involves working effectively with others to achieve shared goals and objectives through cooperation and coordination.",
    },
    {
        "name": "Time Management",
        "description": "Time management is the ability to plan and control how you spend the hours in your day to effectively accomplish your goals.",
    },
    {
        "name": "Critical Thinking",
        "description": "Critical thinking is the objective analysis and evaluation of an issue in order to form a judgment.",
    },
    # Technical skills
    {
        "name": "Software Development",
        "description": "Software development is the process of conceiving, specifying, designing, programming, documenting, testing, and bug fixing involved in creating and maintaining applications.",
    },
    {
        "name": "Database Management",
        "description": "Database management involves organizing, storing, and retrieving data efficiently using database management systems and SQL.",
    },
    {
        "name": "Web Development",
        "description": "Web development involves building and maintaining websites and web applications using various programming languages and frameworks.",
    },
    {
        "name": "Cloud Computing",
        "description": "Cloud computing involves delivering computing services including servers, storage, databases, networking, software, analytics, and intelligence over the Internet.",
    },
    {
        "name": "Cybersecurity",
        "description": "Cybersecurity is the practice of protecting systems, networks, and programs from digital attacks and unauthorized access.",
    },
    {
        "name": "Machine Learning",
        "description": "Machine learning is a subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed.",
    },
    {
        "name": "Network Administration",
        "description": "Network administration involves managing and maintaining computer networks, including hardware, software, and security protocols.",
    },
    {
        "name": "Quality Assurance",
        "description": "Quality assurance involves systematic activities to ensure that products and services meet specified requirements and standards.",
    },
    # Marketing and Sales
    {
        "name": "Digital Marketing",
        "description": "Digital marketing involves promoting products or services using digital technologies, mainly on the Internet, but also including mobile phones and other digital media.",
    },
    {
        "name": "Social Media Management",
        "description": "Social media management involves creating, scheduling, analyzing, and engaging with content posted on social media platforms.",
    },
    {
        "name": "Content Creation",
        "description": "Content creation involves developing and producing engaging material for various media platforms to inform, educate, or entertain an audience.",
    },
    {
        "name": "Sales Strategy",
        "description": "Sales strategy involves developing plans and tactics to effectively sell products or services and achieve revenue targets.",
    },
    {
        "name": "Market Research",
        "description": "Market research involves gathering, analyzing, and interpreting information about a market, product, or service to inform business decisions.",
    },
    {
        "name": "Brand Management",
        "description": "Brand management involves developing and maintaining a brand's image, reputation, and market position through strategic marketing activities.",
    },
    # Finance and Accounting
    {
        "name": "Financial Analysis",
        "description": "Financial analysis involves evaluating businesses, projects, budgets, and other finance-related transactions to determine their performance and suitability.",
    },
    {
        "name": "Accounting",
        "description": "Accounting involves recording, measuring, and communicating financial information about a business or organization.",
    },
    {
        "name": "Budget Management",
        "description": "Budget management involves planning, monitoring, and controlling financial resources to achieve organizational objectives within allocated funds.",
    },
    {
        "name": "Tax Preparation",
        "description": "Tax preparation involves calculating, filing, and managing tax obligations for individuals or organizations in compliance with tax laws.",
    },
    {
        "name": "Risk Management",
        "description": "Risk management involves identifying, analyzing, and responding to risk factors that could impact an organization's operations and objectives.",
    },
    # Operations and Supply Chain
    {
        "name": "Supply Chain Management",
        "description": "Supply chain management involves overseeing the flow of goods, information, and finances from suppliers to customers.",
    },
    {
        "name": "Logistics Coordination",
        "description": "Logistics coordination involves managing the efficient flow and storage of goods, services, and information from point of origin to point of consumption.",
    },
    {
        "name": "Inventory Management",
        "description": "Inventory management involves overseeing and controlling the ordering, storage, and use of components and products.",
    },
    {
        "name": "Process Improvement",
        "description": "Process improvement involves analyzing and enhancing business processes to increase efficiency, reduce costs, and improve quality.",
    },
    {
        "name": "Quality Control",
        "description": "Quality control involves monitoring and testing products or services to ensure they meet specified standards and requirements.",
    },
    # Human Resources
    {
        "name": "Recruitment",
        "description": "Recruitment involves identifying, attracting, and selecting qualified candidates for job openings within an organization.",
    },
    {
        "name": "Training and Development",
        "description": "Training and development involves enhancing employee skills, knowledge, and capabilities to improve performance and career growth.",
    },
    {
        "name": "Performance Management",
        "description": "Performance management involves setting expectations, monitoring progress, and providing feedback to help employees achieve their goals.",
    },
    {
        "name": "Employee Relations",
        "description": "Employee relations involves managing the relationship between employers and employees to maintain a positive and productive work environment.",
    },
    # Creative and Design
    {
        "name": "Graphic Design",
        "description": "Graphic design involves creating visual content to communicate messages through typography, imagery, color, and form.",
    },
    {
        "name": "User Experience Design",
        "description": "User experience design involves designing products that provide meaningful and relevant experiences to users.",
    },
    {
        "name": "Video Production",
        "description": "Video production involves planning, shooting, and editing video content for various purposes including marketing, education, and entertainment.",
    },
    {
        "name": "Photography",
        "description": "Photography involves capturing and creating images using cameras and various photographic techniques.",
    },
    {
        "name": "Creative Writing",
        "description": "Creative writing involves producing original written works including fiction, poetry, screenplays, and other literary forms.",
    },
    # Healthcare and Science
    {
        "name": "Healthcare Administration",
        "description": "Healthcare administration involves managing the operations, finances, and policies of healthcare facilities and organizations.",
    },
    {
        "name": "Research Methods",
        "description": "Research methods involve systematic approaches to gathering, analyzing, and interpreting data to answer research questions.",
    },
    {
        "name": "Statistical Analysis",
        "description": "Statistical analysis involves collecting, organizing, analyzing, and interpreting numerical data to identify patterns and trends.",
    },
    {
        "name": "Laboratory Techniques",
        "description": "Laboratory techniques involve specialized procedures and methods used in scientific research and analysis.",
    },
    # Education and Training
    {
        "name": "Curriculum Development",
        "description": "Curriculum development involves designing, implementing, and evaluating educational programs and learning experiences.",
    },
    {
        "name": "Instructional Design",
        "description": "Instructional design involves creating educational and training materials that facilitate effective learning and knowledge transfer.",
    },
    {
        "name": "Educational Technology",
        "description": "Educational technology involves using technology tools and platforms to enhance teaching and learning experiences.",
    },
    {
        "name": "Adult Learning",
        "description": "Adult learning involves understanding and applying principles and practices specific to educating adult learners.",
    },
]

# Course data for generating CourseLearningExperience
COURSES = [
    # Computer Science Courses
    {
        "name": "Introduction to Programming",
        "code": "CS101",
        "credits": 3.0,
        "description": "Fundamentals of computer programming using modern programming languages.",
    },
    {
        "name": "Data Structures and Algorithms",
        "code": "CS201",
        "credits": 4.0,
        "description": "Study of fundamental data structures and algorithms for efficient computing.",
    },
    {
        "name": "Database Systems",
        "code": "CS301",
        "credits": 3.0,
        "description": "Design and implementation of database systems and data management.",
    },
    {
        "name": "Software Engineering",
        "code": "CS401",
        "credits": 3.0,
        "description": "Principles and practices of software development and project management.",
    },
    # Business Courses
    {
        "name": "Business Analytics",
        "code": "BUS301",
        "credits": 3.0,
        "description": "Application of data analysis techniques to business decision making.",
    },
    {
        "name": "Project Management",
        "code": "BUS401",
        "credits": 3.0,
        "description": "Principles and methodologies for effective project planning and execution.",
    },
    {
        "name": "Strategic Management",
        "code": "BUS501",
        "credits": 3.0,
        "description": "Strategic planning and competitive analysis for organizational success.",
    },
    # Mathematics Courses
    {
        "name": "Statistics",
        "code": "MATH301",
        "credits": 3.0,
        "description": "Statistical methods and analysis for data interpretation.",
    },
    {
        "name": "Calculus I",
        "code": "MATH201",
        "credits": 4.0,
        "description": "Differential and integral calculus of single variable functions.",
    },
    # Science Courses
    {
        "name": "Introduction to Biology",
        "code": "BIO101",
        "credits": 4.0,
        "description": "Fundamental principles of biological sciences and living organisms.",
    },
    {
        "name": "Chemistry Fundamentals",
        "code": "CHEM101",
        "credits": 4.0,
        "description": "Basic principles of chemistry including atomic structure and chemical reactions.",
    },
    # Liberal Arts
    {
        "name": "Technical Writing",
        "code": "ENG301",
        "credits": 3.0,
        "description": "Professional writing skills for technical and business communication.",
    },
    {
        "name": "Ethics in Technology",
        "code": "PHIL201",
        "credits": 3.0,
        "description": "Ethical considerations in technology development and implementation.",
    },
]

# Credential types for generating CredentialAward
CREDENTIALS = [
    {"name": "Proficiency Certificate", "type": "Certificate", "id_prefix": "cert-prof"},
    {"name": "Competency Badge", "type": "Badge", "id_prefix": "badge-comp"},
    {"name": "Skill Verification", "type": "Verification", "id_prefix": "verify-skill"},
]

# Organization data for CredentialAward and CourseLearningExperience
ORGANIZATION_DATA = {
    "Org1": {
        "name": "State University",
        "description": "State University (StateU) is an accredited online university offering online bachelor's and master's degree programs. The programs are competency-based, student-focused, online, nonprofit university.",
        "contact": {
            "address": {
                "addressCity": "Dallas",
                "countryCode": "US",
                "addressState": "Texas",
                "addressStreet": "632 East Hwy 3",
                "addressPostalCode": "75001",
            },
            "email": ["credentials@stateu.edu"],
            "websiteAddress": "https://www.stateu.edu/",
            "telephone": ["111-222-3333"],
        },
        "imageUrl": "https://assets.stateu.edu/99da0cfd314920b5cf8cb6c8727e7675",
        "identifiers": [
            {"identifier": "833333326", "identifierType": "Federal employer identification number"},
            {"identifier": "23323331", "identifierType": "Dun and Bradstreet number"},
            {
                "identifier": "https://credentialfinder.org/organization/000/State_University",
                "identifierType": "credentialfinder.org",
            },
        ],
        "identificationSystem": "State University SIS",
        "accreditation": {
            "accreditingAgency": "Northwest Commission on Colleges and Universities",
            "accreditationType": "Institutional",
            "dateAccredited": "1999-01-01",
            "accreditationStatus": "Active",
        },
    },
    "Org3": {
        "name": "Summit Valley University",
        "description": "Summit Valley University (SVU) is a for-profit online university offering career-focused associate, bachelor's, and master's degree programs. SVU delivers instruction through traditional term-based courses led by experienced faculty. With an emphasis on practical skills and industry alignment, SVU serves a diverse student population seeking flexible, accessible pathways to advancement in business, healthcare, information technology, and criminal justice.",
        "contact": {
            "address": {
                "addressCity": "Aspen Falls",
                "countryCode": "US",
                "addressState": "Colorado",
                "addressStreet": "123 Innovation Drive, Suite 500",
                "addressPostalCode": "80901",
            },
            "email": ["info@summitvalley.edu"],
            "websiteAddress": "https://www.summitvalley.edu/",
            "telephone": ["888-555-7210"],
        },
        "imageUrl": "https://cdn.summitvalley.edu/assets/logo.svg",
        "identifiers": [
            {"identifier": "999112233", "identifierType": "Federal employer identification number"},
            {"identifier": "123456789", "identifierType": "Dun and Bradstreet number"},
            {
                "identifier": "https://credentialfinder.org/organization/999/Summit_Valley_University",
                "identifierType": "credentialfinder.org",
            },
        ],
        "identificationSystem": "stateu-state-university-id",
        "accreditation": {
            "accreditingAgency": "Higher Learning Commission",
            "accreditationType": "Institutional",
            "dateAccredited": "2020-01-01",
            "accreditationStatus": "Active",
        },
    },
}

POSITIONS = [
    # Technology roles
    {
        "name": "Software Developer Intern",
        "description": "Assisted in developing web applications using modern frameworks and technologies.",
        "organization": "Tech Solutions Inc.",
        "ein": "999999950",
    },
    {
        "name": "Data Analyst",
        "description": "Analyzed large datasets to identify trends and patterns, created reports and dashboards for stakeholders.",
        "organization": "Analytics Pro Corp",
        "ein": "999999970",
    },
    {
        "name": "IT Support Specialist",
        "description": "Provided technical support and troubleshooting for hardware and software issues across the organization.",
        "organization": "TechHelp Solutions",
        "ein": "999999971",
    },
    {
        "name": "Web Developer",
        "description": "Designed and developed responsive websites using HTML, CSS, JavaScript, and various frameworks.",
        "organization": "Digital Designs LLC",
        "ein": "999999972",
    },
    {
        "name": "Quality Assurance Tester",
        "description": "Tested software applications for bugs and usability issues, documented findings and worked with development teams.",
        "organization": "QualityFirst Testing",
        "ein": "999999973",
    },
    # Business and Finance
    {
        "name": "Marketing Assistant",
        "description": "Supported marketing campaigns and social media management for small business clients.",
        "organization": "Creative Marketing Group",
        "ein": "999999951",
    },
    {
        "name": "Financial Analyst Intern",
        "description": "Assisted with financial modeling, budget analysis, and preparation of financial reports.",
        "organization": "Financial Advisory Services",
        "ein": "999999974",
    },
    {
        "name": "Sales Associate",
        "description": "Provided customer service, processed sales transactions, and maintained product displays.",
        "organization": "Retail Excellence Corp",
        "ein": "999999975",
    },
    {
        "name": "Account Coordinator",
        "description": "Managed client accounts, coordinated project deliverables, and maintained client relationships.",
        "organization": "Professional Services Inc",
        "ein": "999999976",
    },
    {
        "name": "Business Analyst",
        "description": "Analyzed business processes, identified improvement opportunities, and documented requirements.",
        "organization": "Business Optimization LLC",
        "ein": "999999977",
    },
    # Education and Research
    {
        "name": "Research Assistant",
        "description": "Conducted literature reviews and data collection for academic research projects.",
        "organization": "University Research Center",
        "ein": "999999952",
    },
    {
        "name": "Teaching Assistant",
        "description": "Assisted professors with course instruction, graded assignments, and provided student support.",
        "organization": "State University",
        "ein": "999999978",
    },
    {
        "name": "Tutor",
        "description": "Provided one-on-one and group tutoring sessions for students in mathematics and science subjects.",
        "organization": "Academic Success Center",
        "ein": "999999979",
    },
    {
        "name": "Lab Assistant",
        "description": "Supported laboratory operations, maintained equipment, and assisted with experiments.",
        "organization": "Research Laboratory Inc",
        "ein": "999999980",
    },
    # Customer Service and Support
    {
        "name": "Customer Service Representative",
        "description": "Provided customer support and resolved inquiries through phone and email channels.",
        "organization": "Service Excellence Corp",
        "ein": "999999953",
    },
    {
        "name": "Technical Support Specialist",
        "description": "Assisted customers with technical issues, provided troubleshooting guidance, and escalated complex problems.",
        "organization": "Tech Support Solutions",
        "ein": "999999981",
    },
    {
        "name": "Call Center Agent",
        "description": "Handled inbound customer calls, processed orders, and provided product information.",
        "organization": "Customer Care Center",
        "ein": "999999982",
    },
    # Healthcare and Social Services
    {
        "name": "Medical Assistant",
        "description": "Assisted healthcare providers with patient care, maintained medical records, and performed administrative duties.",
        "organization": "Community Health Clinic",
        "ein": "999999983",
    },
    {
        "name": "Social Work Intern",
        "description": "Provided support services to clients, conducted assessments, and assisted with case management.",
        "organization": "Family Services Agency",
        "ein": "999999984",
    },
    {
        "name": "Pharmacy Technician",
        "description": "Assisted pharmacists with prescription processing, inventory management, and customer service.",
        "organization": "City Pharmacy",
        "ein": "999999985",
    },
    # Operations and Logistics
    {
        "name": "Operations Assistant",
        "description": "Supported daily operations, maintained records, and coordinated with various departments.",
        "organization": "Operations Management Co",
        "ein": "999999986",
    },
    {
        "name": "Warehouse Associate",
        "description": "Managed inventory, processed shipments, and maintained warehouse organization and safety standards.",
        "organization": "Logistics Solutions Inc",
        "ein": "999999987",
    },
    {
        "name": "Administrative Assistant",
        "description": "Provided administrative support including scheduling, correspondence, and document preparation.",
        "organization": "Professional Administration LLC",
        "ein": "999999988",
    },
    # Creative and Media
    {
        "name": "Graphic Design Intern",
        "description": "Created visual designs for marketing materials, websites, and print publications.",
        "organization": "Creative Studios",
        "ein": "999999989",
    },
    {
        "name": "Content Writer",
        "description": "Developed written content for websites, blogs, social media, and marketing materials.",
        "organization": "Content Creation Agency",
        "ein": "999999990",
    },
    {
        "name": "Social Media Coordinator",
        "description": "Managed social media accounts, created content calendars, and analyzed engagement metrics.",
        "organization": "Digital Marketing Pro",
        "ein": "999999991",
    },
    # Hospitality and Retail
    {
        "name": "Hotel Front Desk Agent",
        "description": "Provided guest services, managed reservations, and handled check-in/check-out procedures.",
        "organization": "Downtown Hotel",
        "ein": "999999992",
    },
    {
        "name": "Restaurant Server",
        "description": "Provided dining service to customers, took orders, and ensured customer satisfaction.",
        "organization": "Family Restaurant",
        "ein": "999999993",
    },
    {
        "name": "Retail Manager",
        "description": "Supervised staff, managed inventory, and ensured excellent customer service standards.",
        "organization": "Retail Chain Store",
        "ein": "999999994",
    },
    # Non-profit and Community
    {
        "name": "Volunteer Coordinator",
        "description": "Recruited and managed volunteers, organized community events, and maintained volunteer records.",
        "organization": "Community Outreach Center",
        "ein": "999999995",
    },
    {
        "name": "Event Planning Assistant",
        "description": "Assisted with planning and coordinating events, managed vendor relationships, and handled logistics.",
        "organization": "Event Management Company",
        "ein": "999999996",
    },
]


def generate_sha256_identifier(first_name: str, last_name: str, org_id: str) -> str:
    """Generate a SHA256 identifier for a user."""
    data = f"{first_name.lower()}{last_name.lower()}{org_id.lower()}".encode("utf-8")
    return f"sha256${hashlib.sha256(data).hexdigest()}"


def generate_email(first_name: str, last_name: str, domain: str) -> str:
    """Generate an email address for a user."""
    first_initial = first_name[0].lower()
    last_name_clean = last_name.lower()
    return f"{first_initial}{last_name_clean}_lifdemo@{domain}"


def generate_phone() -> str:
    """Generate a random phone number."""
    area_code = random.randint(200, 999)
    exchange = random.randint(200, 999)
    number = random.randint(1000, 9999)
    return f"+1{area_code}{exchange}{number}"


def generate_credential_award(org_id: str, credentialee_name: str) -> Dict[str, Any]:
    """Generate a CredentialAward structure for a given organization and person."""
    credential = random.choice(CREDENTIALS)
    org_data = ORGANIZATION_DATA.get(org_id, ORGANIZATION_DATA["Org1"])

    # Generate a unique credential ID
    credential_id = f"{credential['id_prefix']}-{str(uuid.uuid4())[:8]}"

    # Generate award date (within last 2 years)
    base_date = datetime.datetime.now() - datetime.timedelta(days=random.randint(30, 730))
    award_date = base_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    credential_award = {
        "informationSourceId": org_id,
        "instanceOfCredential": [
            {
                "informationSourceId": org_id,
                "id": credential_id,
                "name": credential["name"],
                "format": ["http://schema.hropenstandards.org/4.4/recruiting/json/ler-rs/LER-RSType.json"],
                "issuedByOrganization": [
                    {
                        "informationSourceId": org_id,
                        "name": org_data["name"],
                        "description": org_data["description"],
                        "Contact": [
                            {
                                "address": [{**org_data["contact"]["address"], "informationSourceId": org_id}],
                                "email": [
                                    {"emailAddress": org_data["contact"]["email"], "informationSourceId": org_id}
                                ],
                                "websiteAddress": org_data["contact"]["websiteAddress"],
                                "telephone": [
                                    {"telephoneNumber": org_data["contact"]["telephone"], "informationSourceId": org_id}
                                ],
                                "informationSourceId": org_id,
                            }
                        ],
                        "imageUrl": org_data["imageUrl"],
                        "Identifier": [
                            {**identifier, "informationSourceId": org_id} for identifier in org_data["identifiers"]
                        ],
                        "identificationSystem": org_data["identificationSystem"],
                        "organizationType": [],
                    }
                ],
                "Accreditation": [{**org_data["accreditation"], "informationSourceId": org_id}],
            }
        ],
        "id": credential_id,
        "awardIssueDate": award_date,
        "credentialAwardee": credentialee_name,
    }

    return credential_award


def generate_course_learning_experience(org_id: str) -> Dict[str, Any]:
    """Generate a CourseLearningExperience structure for a given organization."""
    course = random.choice(COURSES)
    org_data = ORGANIZATION_DATA.get(org_id, ORGANIZATION_DATA["Org1"])

    # Generate course dates (within last 3 years)
    end_date = datetime.datetime.now() - datetime.timedelta(days=random.randint(30, 1095))
    start_date = end_date - datetime.timedelta(days=random.randint(60, 120))  # Course duration 2-4 months

    course_experience = {
        "informationSourceId": org_id,
        "assertedByOrganization": [
            {
                "informationSourceId": org_id,
                "name": org_data["name"],
                "description": org_data["description"],
                "Contact": [
                    {
                        "address": [{**org_data["contact"]["address"], "informationSourceId": org_id}],
                        "email": [{"emailAddress": org_data["contact"]["email"], "informationSourceId": org_id}],
                        "websiteAddress": org_data["contact"]["websiteAddress"],
                        "telephone": [
                            {"telephoneNumber": org_data["contact"]["telephone"], "informationSourceId": org_id}
                        ],
                        "informationSourceId": org_id,
                    }
                ],
                "imageUrl": org_data["imageUrl"],
                "Identifier": [{**identifier, "informationSourceId": org_id} for identifier in org_data["identifiers"]],
                "identificationSystem": org_data["identificationSystem"],
                "organizationType": [],
            }
        ],
        "course": [
            {
                "informationSourceId": org_id,
                "courseCreditValue": course["credits"],
                "courseEndDate": end_date.strftime("%Y-%m-%dT%H:%M:%S"),
                "courseBeginDate": start_date.strftime("%Y-%m-%dT%H:%M:%S"),
                "accreditedByOrganization": [
                    {
                        "identificationSystem": f"{org_data['identificationSystem'].lower().replace(' ', '-')}-accrediting-commission-id",
                        "name": "Accrediting Commission",
                        "organizationType": ["Accreditor"],
                        "informationSourceId": org_id,
                    }
                ],
                "approvedByOrganization": [
                    {
                        "identificationSystem": f"{org_data['identificationSystem'].lower().replace(' ', '-')}-state-department-of-education-id",
                        "name": "State Department of Education",
                        "organizationType": ["Government Agency"],
                        "informationSourceId": org_id,
                    }
                ],
                "Identifier": [
                    {
                        "identifier": course["code"],
                        "identifierType": "Course Code",
                        "identifierVerification": ["Academic Records"],
                        "informationSourceId": org_id,
                    }
                ],
            }
        ],
    }

    return course_experience


def generate_user_data(first_name: str, last_name: str, org_id: str, org_config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate complete user data for a specific organization."""

    # Basic user info
    city, state, zip_code = random.choice(CITIES_STATES)
    email = generate_email(first_name, last_name, org_config["domain"])
    phone = generate_phone()
    sha_id = generate_sha256_identifier(first_name, last_name, org_id)
    school_id = f"{org_config['school_id_prefix']}{org_config['next_id']:03d}"

    # Base user structure
    user_data = {
        "person": [
            {
                "name": [{"informationSourceId": org_id, "lastName": last_name, "firstName": first_name}],
                "contact": [
                    {
                        "email": [{"informationSourceId": org_id, "emailAddress": [email]}],
                        "address": [
                            {
                                "informationSourceId": org_id,
                                "addressCity": city,
                                "countryCode": "US",
                                "addressState": state,
                                "addressPostalCode": zip_code,
                            }
                        ],
                        "telephone": [{"informationSourceId": org_id, "telephoneNumber": [phone]}],
                    }
                ],
                "identifier": [
                    {
                        "informationSourceId": org_id,
                        "identifier": sha_id,
                        "identifierType": "INSTITUTION_ASSIGNED_NUMBER",
                    },
                    {
                        "informationSourceId": org_id,
                        "identifier": school_id,
                        "identifierType": "School-assigned number",
                    },
                ],
            }
        ]
    }

    # Add university ID for Org3
    if org_id == "Org3":
        university_id = f"{org_config['university_id_prefix']}{org_config['next_id']}"
        user_data["person"][0]["identifier"].append(
            {
                "informationSourceId": org_id,
                "identifier": university_id,
                "identifierType": "Summit Valley University student ID",
            }
        )

    # Add some skills (randomly select 3-6 skills)
    num_skills = random.randint(3, 6)
    selected_skills = random.sample(SKILLS, num_skills)

    proficiency_list = []
    for skill in selected_skills:
        proficiency_entry = {"informationSourceId": org_id, "name": skill["name"], "description": skill["description"]}

        # Add CredentialAward for some skills in Org1 and Org3 only
        if org_id in ["Org1", "Org3"] and random.random() < 0.4:  # 40% chance to have credential
            full_name = f"{first_name} {last_name}"
            credential_award = generate_credential_award(org_id, full_name)
            proficiency_entry["CredentialAward"] = [credential_award]

        proficiency_list.append(proficiency_entry)

    if proficiency_list:
        user_data["person"][0]["proficiency"] = proficiency_list

    # Add employment experience (randomly select 1-2 positions)
    num_positions = random.randint(1, 2)
    selected_positions = random.sample(POSITIONS, num_positions)

    employment_list = []
    for i, position in enumerate(selected_positions):
        start_year = 2020 + i
        end_year = start_year + random.randint(1, 2)

        employment_list.append(
            {
                "informationSourceId": org_id,
                "name": position["name"],
                "endDate": f"{end_year}-{random.randint(1, 12):02d}",
                "position": [
                    {
                        "description": position["description"],
                        "offeredByOrganization": [
                            {
                                "informationSourceId": org_id,
                                "name": position["organization"],
                                "identifier": [
                                    {
                                        "identifier": position["ein"],
                                        "identifierType": "Federal employer identification number",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "startDate": f"{start_year}-{random.randint(1, 12):02d}",
            }
        )

    if employment_list:
        user_data["person"][0]["employmentLearningExperience"] = employment_list

    # Add course learning experiences for Org1 and Org3 only
    if org_id in ["Org1", "Org3"]:
        num_courses = random.randint(2, 4)  # 2-4 courses per user
        course_experiences = []
        for _ in range(num_courses):
            course_experience = generate_course_learning_experience(org_id)
            course_experiences.append(course_experience)

        if course_experiences:
            user_data["person"][0]["CourseLearningExperience"] = course_experiences

    # Add position preferences (simplified)
    user_data["person"][0]["positionPreferences"] = [
        {
            "informationSourceId": org_id,
            "travel": [{"percentage": None, "willingToTravelIndicator": None}],
            "relocation": [{"willingToRelocateIndicator": None}],
            "remoteWork": [{"remoteWorkIndicator": None}],
            "positionTitles": [],
            "positionOfferingTypeCodes": [],
            "offeredRemunerationPackage": [
                {"ranges": [{"minimumAmount": [{"value": None, "currency": None}]}], "basisCode": None}
            ],
        }
    ]

    # Add employment preferences
    user_data["person"][0]["employmentPreferences"] = [
        {
            "informationSourceId": org_id,
            "offeredByOrganization": [
                {
                    "informationSourceId": org_id,
                    "name": None,
                    "identifier": [{"informationSourceId": org_id, "identifier": None, "identifierType": None}],
                }
            ],
            "organizationTypes": [],
        }
    ]

    return user_data


def generate_users(num_users: int, output_dir: Path = None) -> None:
    """Generate the specified number of users across all 3 demo orgs."""

    if output_dir is None:
        output_dir = SAMPLE_DATA_DIR

    # Calculate maximum possible unique name combinations
    max_combinations = len(FIRST_NAMES) * len(LAST_NAMES)
    if num_users > max_combinations:
        print(f"Warning: Requested {num_users} users but only {max_combinations} unique name combinations available.")
        print("Some users may have duplicate names. Consider adding more names to the lists.")

    print(f"Generating {num_users} users across 3 demo organizations...")
    print(f"Available name combinations: {max_combinations}")

    # Ensure output directories exist
    for org_name in ORG_CONFIG.keys():
        org_dir = output_dir / org_name
        org_dir.mkdir(parents=True, exist_ok=True)

    # Track used names to avoid duplicates when possible
    used_names = set()

    # Generate users
    for i in range(num_users):
        # Try to find an unused name combination
        attempts = 0
        max_attempts = 100  # Prevent infinite loop

        while attempts < max_attempts:
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            name_combo = (first_name, last_name)

            if name_combo not in used_names or len(used_names) >= max_combinations:
                used_names.add(name_combo)
                break
            attempts += 1

        if attempts >= max_attempts and len(used_names) < max_combinations:
            print(f"Warning: Could not find unique name combination for user {i + 1}, using random selection")

        print(f"Generating user {i + 1}/{num_users}: {first_name} {last_name}")

        # Create user in each organization
        for org_name, org_config in ORG_CONFIG.items():
            org_id = org_config["id"]

            # Generate user data
            user_data = generate_user_data(first_name, last_name, org_id, org_config)

            # Write to file
            filename = f"{first_name}-{last_name}-generated.json"
            file_path = output_dir / org_name / filename

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(user_data, f, indent=2, ensure_ascii=False)

            print(f"  Created: {file_path}")

            # Increment the next ID for this org
            ORG_CONFIG[org_name]["next_id"] += 1

    print(f"\nSuccessfully generated {num_users} users across all 3 demo organizations!")
    print(f"Files saved to: {output_dir}")
    print(f"Total files created: {num_users * 3}")
    if len(used_names) < num_users:
        duplicates = num_users - len(used_names)
        print(f"Note: {duplicates} duplicate name(s) were created due to limited name combinations")


def main():
    """Main function to parse arguments and generate users."""
    parser = argparse.ArgumentParser(
        description="Generate additional sample user data across the 3 demo organizations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_sample_users.py --num-users 5
  python generate_sample_users.py --num-users 10 --output-dir /custom/path
        """,
    )

    parser.add_argument(
        "--num-users", type=int, required=True, help="Number of users to generate across all 3 demo organizations"
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for generated files (default: projects/mongodb/sample_data)",
    )

    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated without creating files")

    args = parser.parse_args()

    if args.num_users <= 0:
        print("Error: Number of users must be greater than 0")
        return 1

    if args.dry_run:
        print(f"DRY RUN: Would generate {args.num_users} users in each of the 3 demo organizations:")
        for org_name in ORG_CONFIG.keys():
            print(f"  - {org_name}")
        print(f"Total files that would be created: {args.num_users * 3}")
        return 0

    try:
        generate_users(args.num_users, args.output_dir)
        return 0
    except Exception as e:
        print(f"Error generating users: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
