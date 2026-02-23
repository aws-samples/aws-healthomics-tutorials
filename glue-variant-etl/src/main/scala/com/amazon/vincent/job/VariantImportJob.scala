// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job

import com.amazon.vincent.job.common.{
  AWSClientProvider,
  DataValidator,
  DownloadReferenceTrait,
  SparkSessionWithCredentialsProvider
}
import com.amazon.vincent.job.components.processors._
import com.amazon.vincent.job.components.{
  DataFrameV2Writer,
  VCFDataFrameLoader,
  VariantJobComponent
}
import com.amazon.vincent.job.logger.VincentGlueLogger
import com.amazon.vincent.job.models.{JobParameterNames, TableFormat, VariantImportJobParameters}
import com.amazonaws.services.glue.GlueContext
import com.amazonaws.services.glue.util.{GlueArgParser, Job}
import io.projectglow.Glow

import scala.collection.JavaConverters._

object VariantImportJob extends DownloadReferenceTrait with SparkSessionWithCredentialsProvider {

  val logger = new VincentGlueLogger

  def main(sysArgs: Array[String]): Unit = {

    sys.props.+=(
      (
        "software.amazon.awssdk.http.service.impl",
        "software.amazon.awssdk.http.urlconnection.UrlConnectionSdkHttpService"))
    val args =
      GlueArgParser.getResolvedOptions(sysArgs, VariantImportJobParameters.glueArgs)

    val params = VariantImportJobParameters(args)
    val spark =
      createSparkSession(params.tablePath)
    val gspark = Glow.register(spark)
    val glueContext: GlueContext = new GlueContext(spark.sparkContext)
    val referenceStoreDao = AWSClientProvider.getReferenceStoreDao()

    val variantJobComponent = VariantJobComponent(
      gspark,
      new DataFrameV2Writer(logger),
      new VCFDataFrameLoader(),
      Seq(
        new VCFLeftNormalizationProcessor(referenceStoreDao, logger),
        VEPAnnotationProcessor(spark, params, logger),
        new ExplodeGenotypeProcessor,
        new AddImportJobIdProcessor,
        new MissingAndAdditionalFieldsProcessor(logger)),
      logger)

    val variantJob = new VariantJob(variantJobComponent)
    Job.init(params.jobName, glueContext, args.asJava)

    val df = variantJob.run(params)

    if (TableFormat.supportsImportDataValidation(params.tableFormat.id)) {
      DataValidator.check(df, glueContext, params.tableLocation, params.jobId)
    }

    Job.commit()
  }
}
