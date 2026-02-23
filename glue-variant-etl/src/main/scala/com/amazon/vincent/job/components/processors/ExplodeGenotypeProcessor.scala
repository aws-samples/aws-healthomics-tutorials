// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components.processors

import com.amazon.vincent.job.models.ImportJobParameters
import org.apache.spark.sql.DataFrame
import org.apache.spark.sql.functions.{array, col, explode, lit, when}

class ExplodeGenotypeProcessor() extends VincentJobProcessor[ImportJobParameters] {

  override def process(
      inputDf: DataFrame,
      vincentJobParameters: ImportJobParameters): DataFrame = {
    val df = inputDf.withColumnRenamed("filters", "original_filters")
    // Use "explode" to duplicate each row for each sample
    val exploded = df
      .withColumn(
        "exp",
        explode(
          when(col("genotypes").isNotNull, col("genotypes"))
            .otherwise(array(lit(null)))))
      .select("*", "exp.*")
      .drop("genotypes", "exp")

    val finalDf = exploded.select(exploded.columns.map(x => col(x).as(x.toLowerCase)): _*)

    finalDf
      .withColumnRenamed("filters", "genotype_filters")
      .withColumnRenamed("original_filters", "filters")
  }
}
