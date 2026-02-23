// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models
import spray.json._
import com.amazon.vincent.job.annotation.FormatOptions
import com.amazon.vincent.job.annotation.FormatOptionsJsonProtocol._
import com.amazon.vincent.job.annotation.vcf.VCFAnnotationOptions
import com.amazon.vincent.job.models.AnnotationImportJobParameters.parseVCFOptions

case class AnnotationImportJobParameters(
    jobName: String,
    databaseName: String,
    tableName: String,
    tablePath: String,
    tableFormat: TableFormat.Value,
    jobId: String,
    inputPath: String,
    referenceArn: String,
    runLeftNormalization: Boolean,
    formatOptions: String,
    storeOptions: String,
    storeFormat: StoreFormat,
    annotationFields: AnnotationFields,
    tableSortKeys: List[String])
    extends ImportJobParameters {
  val vcfOptions: VCFAnnotationOptions = parseVCFOptions(formatOptions)

  val glueArgs: Array[String] = AnnotationImportJobParameters.glueArgs
  val referenceStoreItem: Option[ReferenceStoreItem] =
    if (referenceArn.nonEmpty) Some(ReferenceStoreItem(referenceArn)) else None

}

object AnnotationImportJobParameters {

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
    JobParameterNames.storeFormat,
    JobParameterNames.formatOptions,
    JobParameterNames.storeOptions,
    JobParameterNames.annotationFields,
    JobParameterNames.tableSortKeys)

  def parseVCFOptions(formatOptions: String): VCFAnnotationOptions = {
    val defaultOptions = VCFAnnotationOptions(Some(false), Some(false))
    if (formatOptions.isEmpty) {
      return defaultOptions
    }
    val jsonAst = formatOptions.parseJson
    jsonAst
      .convertTo[FormatOptions]
      .vcfOptions
      .getOrElse(defaultOptions)
  }

  def apply(values: Map[String, String]): AnnotationImportJobParameters = {
    new AnnotationImportJobParameters(
      jobName = values(JobParameterNames.jobName),
      databaseName = values(JobParameterNames.databaseName),
      tableName = values(JobParameterNames.tableName),
      tablePath = values(JobParameterNames.tablePath),
      tableFormat = TableFormat.withName(values(JobParameterNames.tableFormat)),
      jobId = values(JobParameterNames.jobId),
      inputPath = values(JobParameterNames.inputPath),
      referenceArn = values(JobParameterNames.referenceArn),
      runLeftNormalization = values(JobParameterNames.runLeftNormalization).toBoolean,
      formatOptions = values(JobParameterNames.formatOptions),
      storeOptions = values(JobParameterNames.storeOptions),
      storeFormat = StoreFormat.withName(values(JobParameterNames.storeFormat)),
      annotationFields = AnnotationFields.fromJsonString(
        values.getOrElse(JobParameterNames.annotationFields, "{}")),
      tableSortKeys =
        TableSortKeys.fromJsonString(values.getOrElse(JobParameterNames.tableSortKeys, "[]")))
  }
}
