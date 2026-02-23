// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components.processors

import com.amazon.vincent.job.logger.LoggerTrait
import com.amazon.vincent.job.models.ImportJobParameters
import com.amazon.vincent.job.models.exceptions.VincentUserException
import com.amazon.vincent.job.models.vep.{AnnotationColumn, VepEntry, VepField, VepFieldGenerator}
import org.apache.spark.sql.expressions.UserDefinedFunction
import org.apache.spark.sql.functions.{col, lit, struct, udf}
import org.apache.spark.sql.{DataFrame, SparkSession}

import scala.util.{Failure, Success, Try}

class VEPAnnotationProcessor(val vepOrder: Option[Array[VepField]] = None, logger: LoggerTrait)
    extends VincentJobProcessor[ImportJobParameters] {

  def getUdf(vepOrder: Array[VepField]): UserDefinedFunction = udf((vepInfoValue: String) => {
    Try {
      VepEntry.fromVepInfoValue(vepInfoValue, vepOrder).toList
    } match {
      case Failure(exception) => {
        // this gets logged in the worker nodes
        println(s"Failed to parse Vep entries for $vepInfoValue. Reason $exception")
        AnnotationColumn(Some(List.empty[VepEntry]))
      }
      case Success(value) =>
        AnnotationColumn(Some(value))
    }
  })

  override def process(
      inputDf: DataFrame,
      vincentJobParameters: ImportJobParameters): DataFrame = {
    if (vincentJobParameters.supportsVEPParsing) {
      logger.info(
        s"Store support vep parsing. Will Attempt to parse VEP annotations with INFO id ${vincentJobParameters.annotationFields.vep.get}")
      vepOrder match {
        case Some(value) => {
          logger.info(
            s"Parsing VEP annotations with the following format: ${value.mkString(",")}")
          val vepUdf = getUdf(value)
          val csq = vincentJobParameters.annotationFields.vep.get
          inputDf.withColumn("annotations", vepUdf(col(s"attributes.$csq")))
        }
        case None =>
          logger.info(
            s"VCF does not contains header indicating VEP annotation is present. Filling annotations.vep with null.")
          inputDf.withColumn("annotations", struct(lit(null).as("vep")))
      }
    } else {
      logger.info("Does not supportVEPParsing")
      inputDf
    }
  }
}

object VEPAnnotationProcessor {
  val infoHeaderPrefix = "##INFO=<ID="
  val commentLinePrefix = "#"

  def apply(
      spark: SparkSession,
      vincentJobParameters: ImportJobParameters,
      logger: LoggerTrait): VEPAnnotationProcessor = {

    if (vincentJobParameters.supportsVEPParsing) {
      logger.info(
        s"Store supports VEP parsing. Retriving format string with ID: ${vincentJobParameters.annotationFields.vep}.")
      val vepEntries = vincentJobParameters.annotationFields.vep match {
        case Some(value) => retrieveFormatString(spark, value, vincentJobParameters.s3aPath)
        case None => None
      }
      logger.info(s"Parsing VEP Entries with $vepEntries")
      new VEPAnnotationProcessor(vepEntries, logger)
    } else {
      logger.info(s"Store does not VEP parsing. Skipping retrieving format string.")
      new VEPAnnotationProcessor(None, logger)
    }

  }

  /**
   * Get VEP format fields from VCF header if they exist
   *
   * Use spark rdd to read the vcf file as text file. Keep reading and filter for lines with the
   * info field or when we pass the headers Stop when we have 2 rows of data. Check if there 2
   * info vep fields - this is an error and throw an exception otherwise if a info vep is found,
   * parse it.
   *
   * @param spark:
   *   spark session
   * @param vepKey:
   *   vepKey used for extraction
   * @param s3aPath:
   *   path to vcf file
   * @return
   *   seq of vep fields.
   */
  def retrieveFormatString(
      spark: SparkSession,
      vepKey: String,
      s3aPath: String): Option[Array[VepField]] = {

    val infoPrefix = s"$infoHeaderPrefix$vepKey"

    val infoData = spark.read
      .textFile(s3aPath)
      .filter(line => line.startsWith(infoPrefix) || !line.startsWith("#"))
      .take(2)

    if (infoData.count(line => line.startsWith(infoPrefix)) == 2) {
      throw new VincentUserException(
        s"Duplicate VEP INFO header with ID: $vepKey found in header.")
    }

    infoData.find(line => line.startsWith(infoPrefix)) match {
      case Some(value) => VepFieldGenerator.fromHeader(value)
      case None => None
    }
  }
}
