// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.gff

import com.amazon.vincent.job.AnnotationJobParameters
import com.amazon.vincent.job.common.{
  DataFrameUtils,
  DataValidator,
  SparkSessionWithCredentialsProvider
}
import com.amazon.vincent.job.models.TableFormat
import com.amazonaws.services.glue.GlueContext
import com.amazonaws.services.glue.log.GlueLogger
import com.amazonaws.services.glue.util.Job
import io.projectglow.Glow
import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.spark.sql.types.{
  ArrayType,
  BooleanType,
  DoubleType,
  IntegerType,
  StringType,
  StructField,
  StructType
}

import scala.collection.JavaConverters._

object GFFImportJob extends SparkSessionWithCredentialsProvider {

  val logger = new GlueLogger

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

    val glueContext: GlueContext = new GlueContext(spark.sparkContext)
    val gspark = Glow.register(spark)
    Job.init(jobArgs(AnnotationJobParameters.jobName), glueContext, args.asJava)

    val s3aPath = jobArgs(AnnotationJobParameters.inputPath).replace("s3://", "s3a://")
    val df = gspark.read
      .format("gff")
      .load(s3aPath)

    // Add JobId to the schema which will be used for a delete API by jobId and sampleId.
    var finalDf =
      df.withColumn("importJobId", lit(jobArgs(AnnotationJobParameters.jobId)))

    // Change all column headers to lowercase as Athena column headers are case insensitive
    finalDf = finalDf.select(finalDf.columns.map(x => col(x).as(x.toLowerCase)): _*)
    finalDf =
      if (finalDf.columns.contains("alias"))
        finalDf.withColumn("alias", concat_ws(",", col("alias")))
      else finalDf

    // GFF Schema
    val gffSchema = StructType(
      Array(
        StructField("importjobid", StringType, true),
        StructField("seqid", StringType, true),
        StructField("source", StringType, true),
        StructField("type", StringType, true),
        StructField("start", IntegerType, true),
        StructField("end", IntegerType, true),
        StructField("score", DoubleType, true),
        StructField("strand", StringType, true),
        StructField("phase", IntegerType, true),
        StructField("id", StringType, true),
        StructField("name", StringType, true),
        StructField("alias", StringType, true),
        StructField("parent", ArrayType(StringType, true), true),
        StructField("target", StringType, true),
        StructField("gap", StringType, true),
        StructField("derivesfrom", StringType, true),
        StructField("note", ArrayType(StringType, true), true),
        StructField("dbxref", ArrayType(StringType, true), true),
        StructField("ontologyterm", ArrayType(StringType, true), true),
        StructField("is_circular", BooleanType, true)))

    // Find intersection between schema sets
    val gffSchemaSet = gffSchema.fieldNames.toSet
    val finalDfDataSet = finalDf.columns.toSet
    logger.info(s"finalDfDataSet $finalDfDataSet")
    val intersectionCol = gffSchemaSet.intersect(finalDfDataSet)
    logger.info(s"intersectionCol $intersectionCol")

    // Find if any missing columns - nullify them
    if (intersectionCol.size < gffSchemaSet.size) {
      // Find missing column
      val missingCol = gffSchemaSet.diff(intersectionCol)
      // Nullify them in the output dataframe
      gffSchema.fields.foreach(col => {
        if (missingCol.contains(col.name)) {
          finalDf = finalDf.withColumn(col.name, lit(null))
        }
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
