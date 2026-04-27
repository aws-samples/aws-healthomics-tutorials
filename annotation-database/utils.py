import boto3
from pyiceberg.catalog import Catalog, load_catalog
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.table.sorting import SortOrder
from pyiceberg.partitioning import PartitionSpec


def create_table(catalog: Catalog,
                 namespace: str,
                 table_name: str,
                 schema: Schema,
                 partition_spec: PartitionSpec = None,
                 sort_order: SortOrder = None) -> Table:
    """Create an Iceberg Table given the relevant information."""

    if catalog.table_exists(f"{namespace}.{table_name}"):
        print(f"Table {namespace}.{table_name} already exists.")
        return catalog.load_table(f"{namespace}.{table_name}")

    create_table_args = {
        "identifier": f"{namespace}.{table_name}",
        "schema": schema,
        "properties": {"format-version": "2"}
    }

    if partition_spec is not None:
        create_table_args["partition_spec"] = partition_spec

    if sort_order is not None:
        create_table_args["sort_order"] = sort_order

    table = catalog.create_table(**create_table_args)
    print(f"Created table: {namespace}.{table_name}")
    print(f"Table location: {table.location()}")
    return table


def create_namespace(catalog: Catalog, namespace: str) -> None:
    """Create a namespace in the Catalog."""
    try:
        catalog.create_namespace(namespace)
        print(f"Created namespace: {namespace}")
    except Exception as e:
        if "already exists" in str(e):
            print(f"Namespace {namespace} already exists.")
        else:
            raise e


def get_aws_account_id() -> str:
    """Get AWS account ID using boto3."""
    sts = boto3.client('sts')
    return sts.get_caller_identity()['Account']


def get_aws_region() -> str:
    """Get AWS region using boto3."""
    session = boto3.session.Session()
    return session.region_name or 'us-east-1'


def load_s3_tables_catalog(bucket_arn: str) -> Catalog:
    """Connect to an S3 Tables Iceberg catalog."""
    region = get_aws_region()
    catalog_config = {
        "type": "rest",
        "warehouse": bucket_arn,
        "uri": f"https://s3tables.{region}.amazonaws.com/iceberg",
        "rest.sigv4-enabled": "true",
        "rest.signing-name": "s3tables",
        "rest.signing-region": region
    }
    catalog = load_catalog("s3tables", **catalog_config)
    return catalog


def retry_operation(operation, *args, max_retries=5, retry_condition=None, **kwargs):
    """Retry an operation with exponential backoff."""
    import time

    retry_count = 0
    last_exception = None

    while retry_count < max_retries:
        try:
            result = operation(*args, **kwargs)
            return result
        except Exception as e:
            retry_count += 1
            last_exception = e

            should_retry = retry_condition(e) if retry_condition else True

            if should_retry and retry_count < max_retries:
                print(f"Operation failed. Retry attempt {retry_count}/{max_retries}...")
                time.sleep(retry_count * 2)
            else:
                raise e

    if last_exception:
        print(f"Failed after {max_retries} attempts.")
        raise last_exception
