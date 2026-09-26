#!/bin/bash
set -e

# Wait for Mongo to start
echo "EP: Waiting for MongoDB to start..."
sleep 5

# If SEED_DATA_KEY is not set, then skip the import of the seed data
if [ -z "${SEED_DATA_KEY}" ]; then
  echo "EP: SEED_DATA_KEY is not set. Skipping seed data import."
else
  # Get SEED_DATA_KEY from environment variable
  echo "EP: Using seed data key: $SEED_DATA_KEY"

  # Combine JSON arrays from all files matching *.json
  echo "EP: Combining all JSON files in /seed_data/$SEED_DATA_KEY/"
  jq -s . /seed_data/${SEED_DATA_KEY}/*.json > /seed-data.json

  # Import into MongoDB
  echo "EP: Importing data into $MONGO_DB.$MONGO_COLLECTION at $MONGO_HOST..."
  mongoimport \
    --db "$MONGO_DB" \
    --collection "$MONGO_COLLECTION" \
    --type json \
    --drop \
    --file /seed-data.json \
    --jsonArray
fi

# Create the person identifier index used by the Query Cache query/save filter.
# Runs whether or not seeding happened (#1243), and after the import when there is one:
# mongoimport --drop drops the collection and its indexes.
# No --host: init scripts run against a temporary mongod that listens on localhost only (#1304).
echo "EP: Creating person_identifier_idx on $MONGO_DB.$MONGO_COLLECTION..."
mongosh --quiet "$MONGO_DB" --eval "
db.getCollection('${MONGO_COLLECTION}').createIndex(
  { 'Person.Identifier.identifier': 1, 'Person.Identifier.identifierType': 1 },
  { name: 'person_identifier_idx' }
);
"
