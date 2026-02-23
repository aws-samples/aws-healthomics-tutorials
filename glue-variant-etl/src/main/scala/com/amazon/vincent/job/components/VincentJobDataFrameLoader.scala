// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components

import com.amazon.vincent.job.common.DataFrameUtils
import com.amazon.vincent.job.models.exceptions.VincentUserException
import htsjdk.tribble.TribbleException
import org.apache.spark.SparkException
import org.apache.spark.sql.{DataFrame, SparkSession}

trait VincentJobDataFrameLoader {
  def load(sparkSession: SparkSession, s3path: String): DataFrame

}

class VCFDataFrameLoader extends VincentJobDataFrameLoader {
  override def load(sparkSession: SparkSession, s3path: String): DataFrame = try {
    sparkSession.read
      .format("vcf")
      .option("flattenInfoFields", "false")
      .option("validationStringency", "strict")
      .load(s3path)
  } catch {
    case e: SparkException =>
      val cause = e.getCause
      cause match {
        case _: TribbleException.InvalidHeader =>
          val errorMsg = DataFrameUtils.matchVcfHeaderErrorMessage(e.getMessage)
          throw new VincentUserException(errorMsg)
        case _: TribbleException =>
          val customerErrorMsg =
            if (e.getMessage.contains("is not a valid type in the VCF specification")) {
              // https://github.com/samtools/htsjdk/blob/5445b9081a057253b66ed15566bba1e1854202e8/src/main/java/htsjdk/variant/vcf/VCFCompoundHeaderLine.java#L240
              "VCF header contains an invalid value for Type. Please ensure header is as per specification."
            } else {
              "VCF header is malformed. Please ensure header is as per specification."
            }
          throw new VincentUserException(customerErrorMsg)
        case _: IllegalArgumentException =>
          val customerErrorMsg = DataFrameUtils.matchVcfHeaderIAExceptionMsg(e.getMessage)
          throw new VincentUserException(customerErrorMsg)
        case _ => throw e
      }
  }
}
