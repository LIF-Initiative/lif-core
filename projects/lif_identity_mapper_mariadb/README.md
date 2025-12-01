# LIF Identity Mapper MariaDB

The **Identity Mapper MariaDB** project provides a docker-based MariaDB database for storing the identity mappings for the Identity Mapper.

# Example Usage

## Build a docker image from root

``` shell
./build-docker.sh
```

## Run the image

``` shell
docker run --rm --name lif_identity_mapper_mariadb -p 3306:3306 lif-identity-mapper-mariadb
```

# Connect to the Database

Use these connection parameters:

- host: localhost (or 127.0.0.1)
- port: 3306
- schema: lif
- user: myuser (default) or value for MARIADB_USER environment variable
- password: mypass (default) or value for MARIADB_PASSWORD environment variable
