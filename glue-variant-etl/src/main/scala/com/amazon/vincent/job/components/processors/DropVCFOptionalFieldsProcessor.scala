// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components.processors

import com.amazon.vincent.job.models.AnnotationImportJobParameters
import org.apache.spark.sql.DataFrame

class DropVCFOptionalFieldsProcessor extends VincentJobProcessor[AnnotationImportJobParameters] {
  override def process(
      inputDf: DataFrame,
      vincentJobParameters: AnnotationImportJobParameters): DataFrame = {
    val vcfOptions = vincentJobParameters.vcfOptions
    var df = inputDf

    vcfOptions.ignoreFilterField match {
      case Some(value) =>
        if (value) {
          df = df.drop("filters")
        }
      case _ =>
    }

    vcfOptions.ignoreQualField match {
      case Some(value) =>
        if (value) {
          df = df.drop("qual")
        }
      case _ =>
    }
    df
  }
}
