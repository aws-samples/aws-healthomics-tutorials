// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job

import com.amazon.vincent.job.components._
import com.amazon.vincent.job.components.processors.VincentJobProcessor
import com.amazon.vincent.job.logger.LoggerTrait
import com.amazon.vincent.job.models.{
  AnnotationImportJobParameters,
  ImportJobParameters,
  VariantImportJobParameters
}
import org.apache.spark.sql.{DataFrame, SparkSession}

abstract class BaseJob[T <: ImportJobParameters](
    val vincentJobComponent: VincentJobComponent[T]) {
  val processors: Iterable[VincentJobProcessor[_ >: T <: ImportJobParameters]] = {
    vincentJobComponent.processors
  }
  val loader: VincentJobDataFrameLoader = vincentJobComponent.dataFrameLoader
  val writer: VincentJobDataFrameWriter = vincentJobComponent.dataFrameWriter
  val sparkSession: SparkSession = vincentJobComponent.sparkSession
  val logger: LoggerTrait = vincentJobComponent.logger

  def run(importParameter: T): DataFrame = {
    logger.info(s"Started Loading input file: ${importParameter.inputPath}")
    var df = loader.load(sparkSession, importParameter.s3aPath)
    logger.info(s"Processing dataframe with $importParameter")
    df = processors.foldLeft(df)((acc, curr) => curr.process(acc, importParameter))
    logger.info(s"Writing file to ${importParameter.tableLocation}")
    writer.write(df, importParameter.tableLocation, importParameter.tableSortKeys)
    df
  }
}

class VariantJob(override val vincentJobComponent: VariantJobComponent)
    extends BaseJob[VariantImportJobParameters](vincentJobComponent)

class AnnotationVCFJob(override val vincentJobComponent: AnnotationVCFJobComponent)
    extends BaseJob[AnnotationImportJobParameters](vincentJobComponent)
