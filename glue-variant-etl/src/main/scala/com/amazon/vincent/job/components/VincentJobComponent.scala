// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components

import com.amazon.vincent.job.components.processors.VincentJobProcessor
import com.amazon.vincent.job.logger.LoggerTrait
import com.amazon.vincent.job.models.{
  AnnotationImportJobParameters,
  ImportJobParameters,
  VariantImportJobParameters
}
import org.apache.spark.sql.SparkSession

trait VincentJobComponent[T <: ImportJobParameters] {
  def sparkSession: SparkSession

  def dataFrameWriter: VincentJobDataFrameWriter

  def dataFrameLoader: VincentJobDataFrameLoader

  def processors: Iterable[VincentJobProcessor[_ >: T <: ImportJobParameters]]

  def logger: LoggerTrait
}

case class VariantJobComponent(
    sparkSession: SparkSession,
    dataFrameWriter: VincentJobDataFrameWriter,
    dataFrameLoader: VincentJobDataFrameLoader,
    processors: Iterable[
      VincentJobProcessor[_ >: VariantImportJobParameters <: ImportJobParameters]],
    logger: LoggerTrait)
    extends VincentJobComponent[VariantImportJobParameters]

case class AnnotationVCFJobComponent(
    sparkSession: SparkSession,
    dataFrameWriter: VincentJobDataFrameWriter,
    dataFrameLoader: VincentJobDataFrameLoader,
    processors: Iterable[
      VincentJobProcessor[_ >: AnnotationImportJobParameters <: ImportJobParameters]],
    logger: LoggerTrait)
    extends VincentJobComponent[AnnotationImportJobParameters]
