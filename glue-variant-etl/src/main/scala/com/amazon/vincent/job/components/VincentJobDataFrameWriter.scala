// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components

import com.amazon.vincent.job.common.DataFrameUtils
import com.amazon.vincent.job.logger.LoggerTrait
import org.apache.spark.SparkException
import org.apache.spark.sql.DataFrame

import scala.util.{Failure, Success, Try}

trait VincentJobDataFrameWriter {
  def write(df: DataFrame, outPath: String, tableSortKeys: List[String]): Unit
}

class DataFrameV2Writer(val logger: LoggerTrait) extends VincentJobDataFrameWriter {
  override def write(df: DataFrame, outPath: String, tableSortKeys: List[String]): Unit = {
    var maxRetries = 7
    var retries = 0
    var succeed = false
    while (!succeed && retries < maxRetries) {
      Try {
        logger.info("sort keys used: " + tableSortKeys.mkString(","))
        DataFrameUtils.appendDF(df, outPath, tableSortKeys)
      } match {
        case Success(_) => succeed = true
        case Failure(exception) if exception.isInstanceOf[SparkException] =>
          retries += 1
          if (retries == maxRetries) {
            throw exception
          }
          // CommitFailedException is swallowed by Spark writer and throw SparkException
          logger.warn(s"SparkException caught, retrying ($retries/$maxRetries)")
        case Failure(exception) => throw exception
      }
    }
  }
}
