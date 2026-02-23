// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

case class VariantImportJobParameters(
    jobName: String,
    databaseName: String,
    tableName: String,
    tablePath: String,
    tableFormat: TableFormat.Value,
    jobId: String,
    inputPath: String,
    referenceArn: String,
    runLeftNormalization: Boolean,
    annotationFields: AnnotationFields,
    tableSortKeys: List[String])
    extends ImportJobParameters {
  val referenceStoreItem: Option[ReferenceStoreItem] = Some(ReferenceStoreItem(referenceArn))
  val glueArgs: Array[String] = VariantImportJobParameters.glueArgs

}

object VariantImportJobParameters {

  val glueArgs: Array[String] = Array(
    JobParameterNames.jobName,
    JobParameterNames.databaseName,
    JobParameterNames.tableName,
    JobParameterNames.tablePath,
    JobParameterNames.tableFormat,
    JobParameterNames.jobId,
    JobParameterNames.inputPath,
    JobParameterNames.referenceArn,
    JobParameterNames.runLeftNormalization,
    JobParameterNames.annotationFields,
    JobParameterNames.tableSortKeys)

  def apply(values: Map[String, String]): VariantImportJobParameters = {
    new VariantImportJobParameters(
      jobName = values(JobParameterNames.jobName),
      databaseName = values(JobParameterNames.databaseName),
      tableName = values(JobParameterNames.tableName),
      tablePath = values(JobParameterNames.tablePath),
      tableFormat = TableFormat.withName(values(JobParameterNames.tableFormat)),
      jobId = values(JobParameterNames.jobId),
      inputPath = values(JobParameterNames.inputPath),
      referenceArn = values(JobParameterNames.referenceArn),
      runLeftNormalization = values(JobParameterNames.runLeftNormalization).toBoolean,
      annotationFields = AnnotationFields.fromJsonString(
        values.getOrElse(JobParameterNames.annotationFields, "{}")),
      tableSortKeys =
        TableSortKeys.fromJsonString(values.getOrElse(JobParameterNames.tableSortKeys, "[]")))
  }
}
