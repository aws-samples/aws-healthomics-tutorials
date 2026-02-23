// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components.processors

import com.amazon.vincent.job.common.DataFrameUtils
import com.amazon.vincent.job.logger.LoggerTrait
import com.amazon.vincent.job.models.{ImportJobParameters, Schema}
import org.apache.spark.sql.DataFrame
import org.apache.spark.sql.functions.lit

class MissingAndAdditionalFieldsProcessor(logger: LoggerTrait)
    extends VincentJobProcessor[ImportJobParameters] {
  override def process(df: DataFrame, vincentJobParameters: ImportJobParameters): DataFrame = {
    val schema = if (vincentJobParameters.supportsVEPParsing) {
      Schema.VariantSchemaWithAnno
    } else {
      Schema.VariantSchema
    }

    // Find intersection between schema sets
    var finalDf = df
    val variantSchemaSet = schema.fieldNames.toSet
    val finalDfDataSet = finalDf.columns.toSet
    logger.info(s"finalDfDataSet $finalDfDataSet")
    val intersectionCol = variantSchemaSet.intersect(finalDfDataSet)
    logger.info(s"intersectionCol $intersectionCol")

    // Find if any missing columns - nullify them
    if (intersectionCol.size < variantSchemaSet.size) {
      // Find missing column
      val missingCol = variantSchemaSet.diff(intersectionCol)
      // Nullify them in the output dataframe
      schema.fields.foreach(col => {
        if (missingCol.contains(col.name)) {
          finalDf = finalDf.withColumn(col.name, lit(null))
        }
      })
    }

    // Add all extra columns to a map called information
    val extraCol = finalDfDataSet.diff(intersectionCol).toList
    logger.info(s"extraCol $extraCol")

    val informationColName = "information"

    if (extraCol.length == 0) {
      // Fill the information column with nulls
      finalDf = finalDf.withColumn(informationColName, lit(null))
    } else {
      finalDf = DataFrameUtils.addExtraColsToInformationCol(finalDf, extraCol, informationColName)
    }
    finalDf
  }
}
