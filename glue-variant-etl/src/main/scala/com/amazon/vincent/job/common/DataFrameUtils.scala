// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import com.amazon.vincent.job.models.exceptions.VincentUserException
import htsjdk.tribble.TribbleException
import org.apache.spark.SparkException
import org.apache.spark.sql.DataFrame
import org.apache.spark.sql.functions.{col, lit, map}
import org.apache.spark.sql.types.StringType

import scala.collection.mutable
import scala.util.matching.Regex

object DataFrameUtils {

  def addExtraColsToInformationCol(
      df: DataFrame,
      extraCols: List[String],
      informationColName: String): DataFrame = {
    val newColumns = extraCols.flatMap(c => List(lit(c), col(c).cast(StringType)))
    df.withColumn(informationColName, map(newColumns: _*)).drop(extraCols: _*)
  }

  def appendDF(df: DataFrame, table: String, sortKeys: List[String]): Unit = {
    try {
      if (sortKeys.isEmpty) {
        df.writeTo(table).append()
      } else {
        df.sortWithinPartitions(sortKeys(0), sortKeys.drop(1): _*).writeTo(table).append()
      }
    } catch {
      case e: SparkException => processSparkException(e)
    }
  }

  def processSparkException(e: SparkException): Unit = {
    val dejaVu = mutable.Set[Throwable]()
    var cause: Throwable = e.getCause

    if ("Malformed records are detected in record parsing".r
        .findFirstMatchIn(e.getMessage)
        .isDefined) {
      throw new VincentUserException(
        "Malformed Input. Please check the content and corresponding data type in input file.")
    }

    // if circular reference is found, throw original exception
    while (cause != null && !dejaVu.contains(cause)) {
      if (cause.isInstanceOf[TribbleException]) {
        val errorMsg = matchErrorMessage(cause.getMessage)
        throw new VincentUserException(errorMsg)
      } else if (cause.isInstanceOf[IllegalArgumentException]) {
        if (cause.getMessage.contains("found in field INFO but isn't defined in the VCFHeader")) {
          throw new VincentUserException(
            "Key found in field INFO but isn't defined in the VCFHeader.")
        } else {
          throw e
        }
      }
      dejaVu.add(cause)
      cause = cause.getCause
    }
    throw e
  }

  def matchErrorMessage(errorMessage: String): String = {
    val errorMessageTemplates = List(
      "The provided VCF file is malformed at approximately line number (\\d+): unparsable vcf record with allele".r,
      "Line (\\d+): there aren't enough columns for line".r,
      "The provided VCF file is malformed at approximately line number (\\d+)".r,
      "Malformed records are detected in record parsing".r)

    val errorMsg = errorMessageTemplates.view.map { errorMsgRegex =>
      errorMsgRegex.findFirstMatchIn(errorMessage)
    } collectFirst { case Some(matchedErrorMsg) => matchedErrorMsg.matched }
    errorMsg.getOrElse("Malformed Input. Please check content of input file.")
  }

  def matchVcfHeaderErrorMessage(errorMessage: String): String = {
    // https://github.com/samtools/htsjdk/blob/5445b9081a057253b66ed15566bba1e1854202e8/src/main/java/htsjdk/variant/vcf/AbstractVCFCodec.java
    // https://github.com/samtools/htsjdk/blob/5445b9081a057253b66ed15566bba1e1854202e8/src/main/java/htsjdk/variant/vcf/VCFCodec.java
    val errorMessageMap = Map(
      "there are not enough columns present in the header line".r -> "VCF header does not have sufficient number of required fields. Please ensure required header fields are present as per specification.",
      "We never saw a header line specifying VCF version".r -> "VCF header does not contain VCF version.",
      "We never saw the required CHROM header line".r -> "VCF header does not contain required CHROM header line (starting with one #).",
      "it does not match a legal column header name".r -> "VCF header contains an illegal field name. Please ensure fields are as per specification.",
      "No VCF header found in".r -> "VCF header was not found in the input VCF file.",
      "is not a supported version".r -> "Unsupported VCF version.",
      "we were expecting column name".r -> "VCF header fields are not in order as defined by specification. Please ensure fields are as per specification.")

    val errorMsg = getCustomerErrorFromErrorMsgMap(errorMessageMap, errorMessage)
    errorMsg.getOrElse("VCF header is malformed. Please ensure header is as per specification.")
  }

  def matchVcfHeaderIAExceptionMsg(errorMessage: String): String = {
    // https://github.com/samtools/htsjdk/blob/5445b9081a057253b66ed15566bba1e1854202e8/src/main/java/htsjdk/variant/vcf/VCFCompoundHeaderLine.java#L261
    // https://github.com/samtools/htsjdk/blob/5445b9081a057253b66ed15566bba1e1854202e8/src/main/java/htsjdk/variant/vcf/VCFSimpleHeaderLine.java#L104
    val errorMessageMap = Map(
      "Invalid count number, with fixed count the number should be 1 or higher".r -> "VCF header contains an invalid count for NUMBER, with fixed count the number should be 1 or higher.",
      "Invalid VCFSimpleHeaderLine".r -> "Invalid VCF Header: field must not be null.")

    val errorMsg = getCustomerErrorFromErrorMsgMap(errorMessageMap, errorMessage)
    errorMsg.getOrElse("Malformed VCF header. Please ensure header is as per specification.")
  }

  private def getCustomerErrorFromErrorMsgMap(
      errorMsgMap: Map[Regex, String],
      errorMsg: String): Option[String] = {
    val customerError = errorMsgMap.view.collectFirst {
      case (regexPattern, customerErrorMsg) if regexPattern.findFirstIn(errorMsg).isDefined =>
        customerErrorMsg
    }
    customerError
  }

}
