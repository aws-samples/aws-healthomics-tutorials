// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

object JobParameterNames {
  val jobName = "JOB_NAME"
  val databaseName = "GLUE_DATABASE_NAME"
  val tableName = "GLUE_TABLE_NAME"
  val tablePath = "GLUE_TABLE_PATH"
  val tableFormat = "TABLE_FORMAT"
  val jobId = "IMPORT_JOB_ID"
  val inputPath = "INPUT_PATH"
  val referenceArn = "REFERENCE_ARN"
  val runLeftNormalization = "RUN_LEFT_NORMALIZATION"
  val storeFormat = "STORE_FORMAT"
  val formatOptions = "FORMAT_OPTIONS"
  val storeOptions = "STORE_OPTIONS"
  val annotationFields = "ANNOTATION_FIELDS"
  val tableSortKeys = "TABLE_SORT_KEYS"
}
