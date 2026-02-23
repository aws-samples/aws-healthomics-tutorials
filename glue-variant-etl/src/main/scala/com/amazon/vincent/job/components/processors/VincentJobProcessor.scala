// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components.processors

import com.amazon.vincent.job.models.ImportJobParameters
import org.apache.spark.sql.DataFrame

trait VincentJobProcessor[T <: ImportJobParameters] {
  def process(inputDf: DataFrame, vincentJobParameters: T): DataFrame
}
