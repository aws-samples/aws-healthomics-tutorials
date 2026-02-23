// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.vcf

import com.amazon.vincent.job.common.{
  AWSClientProvider,
  DataValidator,
  DownloadReferenceTrait,
  SparkSessionWithCredentialsProvider
}
import com.amazon.vincent.job.components.processors.{
  AddImportJobIdProcessor,
  DropVCFOptionalFieldsProcessor,
  ExplodeGenotypeProcessor,
  MissingAndAdditionalFieldsProcessor,
  VCFLeftNormalizationProcessor,
  VEPAnnotationProcessor
}
import com.amazon.vincent.job.components.{
  AnnotationVCFJobComponent,
  DataFrameV2Writer,
  VCFDataFrameLoader
}
import com.amazon.vincent.job.logger.VincentGlueLogger
import com.amazon.vincent.job.models.{AnnotationImportJobParameters, TableFormat}
import com.amazon.vincent.job.{AnnotationJobParameters, AnnotationVCFJob}
import com.amazonaws.services.glue.GlueContext
import com.amazonaws.services.glue.util.Job
import io.projectglow.Glow

import scala.collection.JavaConverters._

case class VCFAnnotationImportJob()
    extends DownloadReferenceTrait
    with SparkSessionWithCredentialsProvider {

  val logger: VincentGlueLogger = new VincentGlueLogger

  def parse(
      jobArgs: Map[AnnotationJobParameters.Value, String],
      args: Map[String, String]): Unit = {

    val params = AnnotationImportJobParameters(args)
    val spark =
      createSparkSession(params.tablePath)

    val glueContext: GlueContext = new GlueContext(spark.sparkContext)
    val gspark = Glow.register(spark)

    val referenceStoreDao = AWSClientProvider.getReferenceStoreDao()

    val annotationVCFComponent = AnnotationVCFJobComponent(
      gspark,
      new DataFrameV2Writer(logger),
      new VCFDataFrameLoader(),
      Seq(
        new VCFLeftNormalizationProcessor(referenceStoreDao, logger),
        VEPAnnotationProcessor.apply(spark, params, logger),
        new ExplodeGenotypeProcessor,
        new AddImportJobIdProcessor,
        new DropVCFOptionalFieldsProcessor,
        new MissingAndAdditionalFieldsProcessor(logger)),
      logger)

    Job.init(jobArgs(AnnotationJobParameters.jobName), glueContext, args.asJava)

    val annotationVCFJob = new AnnotationVCFJob(annotationVCFComponent)

    val df = annotationVCFJob.run(params)

    if (TableFormat.supportsImportDataValidation(params.tableFormat.id)) {
      DataValidator.check(df, glueContext, params.tableLocation, params.jobId)
    }

    Job.commit()
  }
}
