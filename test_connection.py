from neo4j import GraphDatabase
from getpass import getpass

URI = "bolt://127.0.0.1:7687"
USERNAME = "neo4j"
PASSWORD = getpass("Enter Neo4j password: ")

driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)

try:
    driver.verify_connectivity()
    print("Connected to Neo4j successfully!")

finally:
    driver.close()