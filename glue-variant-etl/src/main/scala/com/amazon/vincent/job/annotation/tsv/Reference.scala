// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import org.apache.spark.sql.types.{IntegerType, StringType, StructField, StructType}
import org.apache.spark.sql.{DataFrame, SparkSession}

import java.nio.file.{Files, Paths}

case class Reference(path: String, refIndex: String) {

  val indexSchema: StructType = StructType(
    Array(
      StructField("NAME", StringType, nullable = false),
      StructField("LENGTH", IntegerType, nullable = false),
      StructField("OFFSET", IntegerType, nullable = false),
      StructField("LINEBASES", IntegerType, nullable = false),
      StructField("LINEWIDTH", IntegerType, nullable = false)))

  def exists(): Boolean = {
    Files.exists(Paths.get(path)) && Files.exists(Paths.get(refIndex))
  }

  def parseIndex(sparkSession: SparkSession): DataFrame = {

    val faiOptions = Map("header" -> "false", "delimiter" -> "\t")
    // use the same sparksession to read the fasta index file
    sparkSession.read
      .format("csv")
      .options(faiOptions)
      .schema(indexSchema)
      .load(refIndex)
      .toDF()
  }

}

object Reference {
  def apply(path: String): Reference = new Reference(path, s"${path}.fai")
}
