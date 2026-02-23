// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import org.apache.spark.sql.DataFrame

// Different annotation types and their relationship between each other
object AnnotationType {
  sealed abstract class AnnotationFormat(val name: String)
  case object UnstructuredAnnotation extends AnnotationFormat("GENERIC")

  sealed abstract class StructuredAnnotation(name: String) extends AnnotationFormat(name)

  // declared as classes to prevent them from extending each other
  sealed abstract class ZeroBase(name: String) extends StructuredAnnotation(name)

  sealed abstract class OneBase(name: String) extends StructuredAnnotation(name)

  case object ChrPos extends OneBase("CHR_POS")

  case object ChrPosRefAlt extends OneBase("CHR_POS_REF_ALT")

  case object ChrStartEndOneBase extends OneBase("CHR_START_END_ONE_BASE")

  case object ChrStartEndRefAltOneBase extends OneBase("CHR_START_END_REF_ALT_ONE_BASE")

  case object ChrStartEndZeroBase extends ZeroBase("CHR_START_END_ZERO_BASE")

  case object ChrStartEndRefAltZeroBase extends ZeroBase("CHR_START_END_REF_ALT_ZERO_BASE")

  // name of inputs
  val inputFormats: Array[String] = Array(
    ChrPos.name,
    ChrPosRefAlt.name,
    ChrStartEndOneBase.name,
    ChrStartEndRefAltOneBase.name,
    ChrStartEndZeroBase.name,
    ChrStartEndRefAltZeroBase.name,
    UnstructuredAnnotation.name)

  def fromName(name: String): AnnotationFormat = {
    name match {
      case ChrPos.name => ChrPos
      case ChrPosRefAlt.name => ChrPosRefAlt
      case ChrStartEndZeroBase.name => ChrStartEndZeroBase
      case ChrStartEndRefAltZeroBase.name => ChrStartEndRefAltZeroBase
      case ChrStartEndOneBase.name => ChrStartEndOneBase
      case ChrStartEndRefAltOneBase.name => ChrStartEndRefAltOneBase
      case _ => UnstructuredAnnotation
    }
  }

  def apply(name: String): AnnotationFormat = {
    fromName(name)
  }
}

/**
 * Classes to hold dataframe, and any other metadata
 *
 * @param dataFrame
 *   Annotation dataFrame
 * @param annotationType
 *   Annotation type
 * @param header
 *   object containing mapping of different annotation field to the name of the columns
 * @param reference
 *   string containg path to reference file. path should be accessible on local disk
 */
case class Annotation(
    dataFrame: DataFrame,
    annotationType: AnnotationType.StructuredAnnotation,
    header: FormatHeader = FormatHeader(),
    reference: Option[Reference])
