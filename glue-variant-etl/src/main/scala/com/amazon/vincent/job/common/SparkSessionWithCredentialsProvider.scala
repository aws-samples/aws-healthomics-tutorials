// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import org.apache.spark.sql.SparkSession

trait SparkSessionWithCredentialsProvider {

  def createSparkSession(tablePath: String): SparkSession = {
    SparkSession
      .builder()
      .config("spark.hadoop.io.compression.codecs", "io.projectglow.sql.util.BGZFCodec")
      .config(
        "spark.hadoop.fs.s3a.aws.credentials.provider",
        "com.amazonaws.auth.DefaultAWSCredentialsProviderChain")
      // Add Iceberg specific configs
      .config("spark.sql.catalog.job_catalog.warehouse", tablePath)
      .config("spark.sql.catalog.job_catalog", "org.apache.iceberg.spark.SparkCatalog")
      .config(
        "spark.sql.catalog.job_catalog.catalog-impl",
        "org.apache.iceberg.aws.glue.GlueCatalog")
      .config("spark.sql.catalog.job_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
      .config("spark.sql.catalog.job_catalog.s3.checksum-enabled", "true")
      .config(
        "spark.sql.extensions",
        "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
      .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
      .config("spark.sql.iceberg.handle-timestamp-without-timezone", "true")
      // Data Encryption
      // At rest encryption
      .config("spark.io.encryption.enabled", "true")
      .config("spark.io.encryption.keySizeBits", "256")
      .config("spark.io.encryption.keygen.algorithm", "HmacSHA256")
      // In-transit encryption
      .config("spark.network.crypto.enabled", "true")
      .config("spark.network.crypto.keyLength", "256")
      .config("spark.network.crypto.keyFactoryAlgorithm", "PBKDF2WithHmacSHA256")
      .getOrCreate()
  }
}
