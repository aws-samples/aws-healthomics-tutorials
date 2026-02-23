// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import com.amazon.vincent.job.AnnotationJobParameters
import com.amazon.vincent.job.annotation.AnnotationStoreOptions
import com.amazon.vincent.job.annotation.FormatOptionsJsonProtocol._
import com.amazon.vincent.job.common.{
  AWSClientProvider,
  DataFrameUtils,
  DataValidator,
  DownloadReferenceTrait,
  SparkSessionWithCredentialsProvider
}
import com.amazon.vincent.job.logger.VincentGlueLogger
import com.amazon.vincent.job.models.{ReferenceStoreItem, TableFormat}
import com.amazonaws.services.glue.GlueContext
import com.amazonaws.services.glue.util.Job
import org.apache.spark.sql.functions._
import org.apache.spark.sql.{DataFrame, SparkSession}
import spray.json._

import scala.collection.JavaConverters._
import scala.collection.mutable.Set

object TSVImportJob extends DownloadReferenceTrait with SparkSessionWithCredentialsProvider {

  val logger = new VincentGlueLogger

  def parse(
      jobArgs: Map[AnnotationJobParameters.Value, String],
      args: Map[String, String]): Unit = {

    val importJobId = jobArgs(AnnotationJobParameters.jobId)
    val tablePath = jobArgs(AnnotationJobParameters.tablePath)
    val tableFormat = jobArgs(AnnotationJobParameters.tableFormat)
    val catalog = "job_catalog"
    val database = jobArgs(AnnotationJobParameters.databaseName)
    val table = jobArgs(AnnotationJobParameters.tableName)
    val tableSortKeys = Nil
    val spark = createSparkSession(tablePath)
    val referenceStoreItem = ReferenceStoreItem(jobArgs(AnnotationJobParameters.referenceArn))

    val referenceDao = AWSClientProvider.getReferenceStoreDao()

    val glueContext: GlueContext = new GlueContext(spark.sparkContext)
    val inputPath = jobArgs(AnnotationJobParameters.inputPath).replace("s3://", "s3a://")
    val runLeftNormalization = jobArgs(AnnotationJobParameters.runLeftNormalization).toBoolean

    val referenceFasta = if (runLeftNormalization) {
      Some(downloadRefToSparkJobs(spark, referenceDao, referenceStoreItem, None))
    } else {
      None
    }
    val config =
      TSVParserConfig.parseFromGlueArgs(
        inputPath,
        jobArgs(AnnotationJobParameters.formatOptions),
        jobArgs(AnnotationJobParameters.storeOptions),
        referenceFasta,
        jobArgs(AnnotationJobParameters.runLeftNormalization).toBoolean)

    val tsvAnnotationParser = TSVAnnotationParser(config, spark)
    val results: DataFrame = tsvAnnotationParser.process()

    Job.init(jobArgs(AnnotationJobParameters.jobName), glueContext, args.asJava)

    // Add JobId to the schema which will be used for a delete API by jobId and sampleId.
    var finalDf =
      results.withColumn("importJobId", lit(jobArgs(AnnotationJobParameters.jobId)))

    // Change all column headers to lowercase as Athena column headers are case insensitive
    finalDf = finalDf.select(finalDf.columns.map(x => col(x).as(x.toLowerCase)): _*)

    // TSV Schema
    val storeOptionsArg = jobArgs(AnnotationJobParameters.storeOptions)
    val storeOptions =
      storeOptionsArg.parseJson.convertTo[AnnotationStoreOptions].tsvStoreOptions.get
    val schemaJsonString = storeOptions.schema.get
    val schemaMap = schemaJsonString.parseJson.convertTo[List[Map[String, String]]]
    var tsvSchemaSet = Set[String]("importjobid")
    schemaMap.map(x => tsvSchemaSet.add(x.keys.head.toLowerCase))

    if (storeOptions.annotationType.get == AnnotationType.ChrPos.name || storeOptions.annotationType.get == AnnotationType.ChrPosRefAlt.name) {
      tsvSchemaSet.add("end")
    }
    logger.info(s"TSV Schema $tsvSchemaSet")

    // Find intersection between schema sets
    val finalDfDataSet = finalDf.columns.toSet
    logger.info(s"Columns from dataframe $finalDfDataSet")
    val intersectionCol = tsvSchemaSet.intersect(finalDfDataSet)
    logger.info(s"Common columns between schema and input $intersectionCol")

    // Find if any missing columns - nullify them
    if (intersectionCol.size < tsvSchemaSet.size) {
      // Find missing column
      val missingCol = tsvSchemaSet.diff(intersectionCol)
      // Nullify them in the output dataframe
      missingCol.toList.foreach(colName => {
        finalDf = finalDf.withColumn(colName, lit(null))
      })
    }

    // Add all extra columns to a map called information
    val extraCol = finalDfDataSet.diff(intersectionCol).toList
    logger.info(s"Any additional columns outside of schema provided $extraCol")
    val informationColName = "information"

    if (extraCol.length == 0) {
      // Fill the information column with nulls
      finalDf = finalDf.withColumn(informationColName, lit(null))
    } else {
      finalDf = DataFrameUtils.addExtraColsToInformationCol(finalDf, extraCol, informationColName)
    }

    val tableLocation = List(catalog, database, table).mkString(".")

    logger.info("sort keys used: " + tableSortKeys.mkString(","))
    DataFrameUtils.appendDF(finalDf, tableLocation, tableSortKeys)

    if (TableFormat.supportsImportDataValidation(TableFormat.version(tableFormat))) {
      DataValidator.check(finalDf, glueContext, tableLocation, importJobId)
    }

    Job.commit()
  }

}
