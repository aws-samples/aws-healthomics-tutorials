// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job

import com.amazon.vincent.job.annotation.gff.GFFImportJob
import com.amazon.vincent.job.annotation.tsv.TSVImportJob
import com.amazon.vincent.job.annotation.vcf.VCFAnnotationImportJob
import com.amazon.vincent.job.models.JobParameterNames
import com.amazonaws.services.glue.util.GlueArgParser

object AnnotationJobParameters extends Enumeration {

  val jobName: AnnotationJobParameters.Value = Value("JOB_NAME")
  val databaseName: AnnotationJobParameters.Value = Value("GLUE_DATABASE_NAME")
  val tableName: AnnotationJobParameters.Value = Value("GLUE_TABLE_NAME")
  val tablePath: AnnotationJobParameters.Value = Value("GLUE_TABLE_PATH")
  val inputPath: AnnotationJobParameters.Value = Value("INPUT_PATH")
  val storeFormat: AnnotationJobParameters.Value = Value("STORE_FORMAT")
  val tableFormat: AnnotationJobParameters.Value = Value("TABLE_FORMAT")
  val formatOptions: AnnotationJobParameters.Value = Value("FORMAT_OPTIONS")
  val storeOptions: AnnotationJobParameters.Value = Value("STORE_OPTIONS")
  val jobId: AnnotationJobParameters.Value = Value("IMPORT_JOB_ID")

  val referenceArn: AnnotationJobParameters.Value = Value("REFERENCE_ARN")
  val runLeftNormalization: AnnotationJobParameters.Value = Value("RUN_LEFT_NORMALIZATION")
  val annotationFields: AnnotationJobParameters.Value = Value(JobParameterNames.annotationFields)

  def stringValues(): Array[String] = {
    AnnotationJobParameters.values.map(value => value.toString).toArray
  }
}

object AnnotationImportJob {
  def main(sysArgs: Array[String]): Unit = {

    val args =
      GlueArgParser.getResolvedOptions(sysArgs, AnnotationJobParameters.stringValues())

    val jobArgs = AnnotationJobParameters.values
      .map(parameter => (parameter, args(parameter.toString)))
      .toMap

    sys.props.+=(
      (
        "software.amazon.awssdk.http.service.impl",
        "software.amazon.awssdk.http.urlconnection.UrlConnectionSdkHttpService"))

    jobArgs.get(AnnotationJobParameters.storeFormat) match {
      case Some("TSV") => TSVImportJob.parse(jobArgs, args)
      case Some("GFF") => GFFImportJob.parse(jobArgs, args)
      case Some("VCF") => VCFAnnotationImportJob().parse(jobArgs, args)
      case other => throw new RuntimeException(s"Unknown annotation type $other")
    }
  }
}
