// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import org.junit.Assert.assertEquals
import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class AnnotationTypeTest extends AnyFunSuite {

  test("Test AnnotationTypeFromName") {
    assertEquals(AnnotationType.fromName("CHR_POS"), AnnotationType.ChrPos)
    assertEquals(AnnotationType.fromName("CHR_POS_REF_ALT"), AnnotationType.ChrPosRefAlt)
    assertEquals(
      AnnotationType.fromName("CHR_START_END_ZERO_BASE"),
      AnnotationType.ChrStartEndZeroBase)
    assertEquals(
      AnnotationType.fromName("CHR_START_END_ONE_BASE"),
      AnnotationType.ChrStartEndOneBase)
    assertEquals(
      AnnotationType.fromName("CHR_START_END_REF_ALT_ZERO_BASE"),
      AnnotationType.ChrStartEndRefAltZeroBase)
    assertEquals(
      AnnotationType.fromName("CHR_START_END_REF_ALT_ONE_BASE"),
      AnnotationType.ChrStartEndRefAltOneBase)
    assertEquals(AnnotationType.fromName("GENERIC"), AnnotationType.UnstructuredAnnotation)
  }
}
